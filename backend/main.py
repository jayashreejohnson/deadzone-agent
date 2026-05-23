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
from tools.orchestrator import run as orchestrate
from seed import seed_if_empty


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    seed_if_empty()
    yield


app = FastAPI(title="DeadZone Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


@app.get("/")
async def root():
    return {"service": "deadzone-agent", "ok": True}


@app.post("/signal")
async def signal(s: Signal):
    """Frontend tells us a user is heading into a dead zone. Orchestrator runs in background."""
    asyncio.create_task(orchestrate(s.model_dump()))
    return {"accepted": True}


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
