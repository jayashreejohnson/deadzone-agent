"""DeadZone Agent — FastAPI app, WebSocket bus, and signal entrypoint.

POST /signal      — frontend reports "user about to hit dead zone"; spawns orchestrator
WS   /ws          — broadcasts every step the agent takes
GET  /dashboard   — aggregate stats for the live dashboard
GET  /static/...  — serves locally-published fallback packs
"""
from __future__ import annotations
import os
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

# Initialize Datadog LLM Observability BEFORE importing anything that uses OpenAI,
# so ddtrace can patch the SDK at import time.
from tools import datadog as dd
dd.init()

from bus import emit, register, unregister
from tools import clickhouse_db as db
from tools import agent1
from tools.orchestrator import run as orchestrate
from seed import seed_if_empty
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import workflow


def _check_env() -> None:
    """Warn loudly at startup about missing env vars that affect functionality."""
    missing_critical = []
    missing_optional = []

    if not os.getenv("OPENROUTER_API_KEY", "").strip():
        missing_critical.append(
            "OPENROUTER_API_KEY — LLM orchestrator will fall back to scripted mode"
        )
    if not os.getenv("AGENT1_URL", "").strip():
        missing_optional.append(
            "AGENT1_URL — dead-zone predictions will use the built-in stub (default: localhost:8001)"
        )
    if not os.getenv("PUBLIC_BASE_URL", "").strip():
        missing_optional.append(
            "PUBLIC_BASE_URL — static pack URLs will default to http://localhost:8000 "
            "(set to https://sunny-appreciation-production.up.railway.app in production)"
        )
    if not os.getenv("NIMBLE_API_KEY", "").strip():
        missing_optional.append("NIMBLE_API_KEY — web search will use stub data")
    if not os.getenv("DD_API_KEY", "").strip() and not os.getenv("DATADOG_API_KEY", "").strip():
        missing_optional.append("DD_API_KEY — Datadog LLM Observability disabled")

    for msg in missing_critical:
        print(f"[startup] WARNING: {msg}")
    for msg in missing_optional:
        print(f"[startup] INFO: {msg}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _check_env()
    db.init_db()
    seed_if_empty()
    yield


app = FastAPI(title="DeadZone Agent", lifespan=lifespan)

# Keep strong references to background tasks so they aren't GC'd mid-flight.
_background_tasks: set[asyncio.Task] = set()

_ALLOWED_ORIGINS = [
    "https://deadzone-production-df6d.up.railway.app",
    # Allow localhost variants for local dev
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static dir for senso fallback packs
_static_dir = Path(__file__).parent / "static"
_static_dir.mkdir(exist_ok=True)
(_static_dir / "packs").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


class Signal(BaseModel):
    user_id: str
    lat: float
    lng: float
    eta_seconds: int = 240
    route_id: str
    deadzone_id: str


class PlanRequest(BaseModel):
    route: str
    departure_time: str  # "17:00"


class PipelineRequest(BaseModel):
    route: str
    departure_time: str
    user_id: str = "user_a"


@app.get("/")
async def root():
    return {"service": "deadzone-agent", "ok": True}


@app.post("/signal")
async def signal(s: Signal):
    """Frontend tells us a user is heading into a dead zone. Orchestrator runs in background."""
    task = asyncio.create_task(orchestrate(s.model_dump()))
    # Hold a strong reference so the task isn't GC'd before it finishes.
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"accepted": True}


@app.post("/plan")
@workflow(name="plan_route")
async def plan(req: PlanRequest):
    """Predict-only: ask Agent 1 for dead zones along the route. Frontend uses this to
    plot zones up-front, then fires /signal as the user approaches each one."""
    raw = await agent1.predict(req.route, req.departure_time)
    zones = agent1.normalize_zones(raw)
    route_id = f"{req.route}@{req.departure_time}".lower().replace(" ", "_")
    LLMObs.annotate(
        input_data=req.model_dump(),
        output_data={"route_id": route_id, "zone_count": len(zones)},
        tags={"workflow": "plan_route"},
    )
    return {
        "route_id": route_id,
        "route": req.route,
        "departure_time": req.departure_time,
        "dead_zones": zones,
        "source": raw.get("_source", "unknown"),
    }


@app.post("/run_pipeline")
@workflow(name="full_pipeline")
async def run_pipeline(req: PipelineRequest):
    """Full Agent 1 → Agent 2 chain: predict zones, then build a pack for each in parallel.
    Returns the assembled content queue (one pack per zone)."""
    raw = await agent1.predict(req.route, req.departure_time)
    zones = agent1.normalize_zones(raw)
    route_id = f"{req.route}@{req.departure_time}".lower().replace(" ", "_")

    LLMObs.annotate(
        input_data=req.model_dump(),
        metadata={"zone_count": len(zones)},
        tags={"workflow": "full_pipeline"},
    )

    async def _build_for_zone(z: dict):
        signal_payload = {
            "user_id": req.user_id,
            "lat": z["lat"], "lng": z["lng"],
            "eta_seconds": (z.get("duration_minutes") or 4) * 60,
            "route_id": route_id,
            "deadzone_id": z["id"],
        }
        await orchestrate(signal_payload)
        # Look up the pack that was just built/bought for this route+zone
        pack = db.find_recent_pack(route_id, z["id"], max_age_min=15)
        return {
            "zone": z,
            "pack": {
                "pack_id": pack["pack_id"] if pack else None,
                "url": pack["url"] if pack else None,
                "owner_user_id": pack["owner_user_id"] if pack else None,
            } if pack else None,
        }

    queue = await asyncio.gather(*[_build_for_zone(z) for z in zones])
    return {
        "route_id": route_id,
        "route": req.route,
        "departure_time": req.departure_time,
        "content_queue": queue,
    }


@app.get("/dashboard")
async def dashboard():
    return db.dashboard_summary()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await register(ws)
    await ws.send_json({"type": "log", "level": "info", "msg": "connected to deadzone-agent"})
    try:
        while True:
            # We don't expect client messages, but keep the connection alive.
            await ws.receive_text()
    except WebSocketDisconnect:
        unregister(ws)
    except Exception:
        unregister(ws)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)
