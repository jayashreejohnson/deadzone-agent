"""Agent 1 client — calls the prediction service (POST /predict) and returns dead zones.

The teammate's Agent 1 endpoint shape (per issue #3):

  POST {AGENT1_URL}/predict
  Body: { "route": "Manhattan to Newark", "departure_time": "17:00" }
  Returns: { "route": "...", "departure_time": "...",
             "dead_zones": { "dead_zones": [ {location: {lat,lon,description},
                                              start_time, duration_minutes, severity}, ... ] } }

If AGENT1_URL is unreachable, a deterministic stub response is returned so the
orchestrator pipeline keeps working in isolation.
"""
from __future__ import annotations
import os
import httpx
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

_AGENT1_URL = os.getenv("AGENT1_URL", "").strip().rstrip("/")
if not _AGENT1_URL:
    _AGENT1_URL = "http://localhost:8001"
    print(
        "[agent1] WARNING: AGENT1_URL env var not set — "
        "defaulting to http://localhost:8001, which will fail in production. "
        "Set AGENT1_URL=https://beneficial-fascination-production.up.railway.app"
    )


def _stub_response(route: str, departure_time: str) -> dict:
    return {
        "route": route,
        "departure_time": departure_time,
        "dead_zones": {
            "dead_zones": [
                {
                    "location": {"lat": 40.7621, "lon": -74.0312,
                                 "description": "Lincoln Tunnel Mid"},
                    "start_time": "17:06", "duration_minutes": 5, "severity": "high",
                },
                {
                    "location": {"lat": 40.7357, "lon": -74.1724,
                                 "description": "Newark McCarter Hwy"},
                    "start_time": "17:16", "duration_minutes": 1, "severity": "low",
                },
            ]
        },
        "_source": "stub",
    }


@tool(name="agent1_predict")
async def predict(route: str, departure_time: str) -> dict:
    """Call Agent 1's /predict endpoint. Returns the parsed JSON response."""
    payload = {"route": route, "departure_time": departure_time}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{_AGENT1_URL}/predict", json=payload)
            resp.raise_for_status()
            data = resp.json()
        data.setdefault("_source", "agent1")
        LLMObs.annotate(
            input_data=payload,
            output_data={"dead_zones_count": _count_zones(data)},
            metadata={"backend": "agent1", "url": _AGENT1_URL},
            tags={"tool": "agent1_predict"},
        )
        return data
    except Exception as e:
        data = _stub_response(route, departure_time)
        LLMObs.annotate(
            input_data=payload,
            output_data={"dead_zones_count": _count_zones(data)},
            metadata={"backend": "stub_after_error", "error": str(e), "url": _AGENT1_URL},
            tags={"tool": "agent1_predict"},
        )
        return data


def _count_zones(resp: dict) -> int:
    try:
        return len(resp["dead_zones"]["dead_zones"])
    except Exception:
        return 0


def normalize_zones(resp: dict) -> list[dict]:
    """Flatten the Agent 1 response into a list of {id, lat, lng, description, ...} dicts."""
    out: list[dict] = []
    try:
        zones = resp["dead_zones"]["dead_zones"]
    except Exception:
        return out
    for i, z in enumerate(zones):
        loc = z.get("location", {})
        out.append({
            "id": f"dz_{i:02d}_{(loc.get('description') or '').lower().replace(' ', '_')[:24]}",
            "lat": loc.get("lat"),
            "lng": loc.get("lon"),
            "description": loc.get("description", f"Zone {i}"),
            "start_time": z.get("start_time"),
            "duration_minutes": z.get("duration_minutes"),
            "severity": z.get("severity"),
        })
    return out
