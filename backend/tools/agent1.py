"""Agent 1 client — predicts dead zones for any driving route.

Primary path: POST {AGENT1_URL}/predict (the original hackathon service).
Fallback: LLM-based prediction via OpenRouter — generates geographically
accurate dead zones from the model's knowledge of tunnels, rural gaps,
underground sections, etc.  Works for any route worldwide.
"""
from __future__ import annotations
import os
import re
import json
import httpx
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

_AGENT1_URL = os.getenv("AGENT1_URL", "").strip().rstrip("/")
_OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

_LLM_SYSTEM = (
    "You are a cellular network coverage expert with deep knowledge of real-world "
    "geography. Your job is to predict where drivers will lose signal on a given route."
)

_LLM_PROMPT = """Predict cellular dead zones for this driving route:

Route: {route}
Departure: {departure_time}

Return ONLY valid JSON — no markdown fences, no explanation, no prose. Use this exact schema:
{{
  "dead_zones": [
    {{
      "location": {{
        "lat": <float>,
        "lon": <float>,
        "description": "<landmark or segment name>"
      }},
      "start_time": "<HH:MM>",
      "duration_minutes": <integer 1-10>,
      "severity": "<high|medium|low>"
    }}
  ]
}}

Guidelines:
- Return 1–4 dead zones that are realistic for this specific route and geography.
- Use accurate lat/lon for the named locations (you know real coordinates).
- Dead zones typically occur at: tunnels, bridges, mountainous terrain, rural highways,
  underground road segments, dense urban canyons, ferry crossings.
- severity: "high" = complete blackout 4+ min, "medium" = intermittent 2-3 min, "low" = brief <2 min.
- If the route has no obvious dead zones, return 1 low-severity zone (urban canyon / bridge).
- start_time should be realistic given the departure time and distance to the zone.
"""


async def _llm_predict(route: str, departure_time: str) -> dict:
    """Use the LLM to predict dead zones when Agent 1 is offline."""
    if not _OPENROUTER_KEY:
        return _hardcoded_fallback(route, departure_time)

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=_OPENROUTER_KEY, base_url="https://openrouter.ai/api/v1")

    prompt = _LLM_PROMPT.format(route=route, departure_time=departure_time)
    resp = await client.chat.completions.create(
        model="google/gemini-2.0-flash-001",
        messages=[
            {"role": "system", "content": _LLM_SYSTEM},
            {"role": "user",   "content": prompt},
        ],
        temperature=0.2,
    )
    raw = resp.choices[0].message.content or ""
    # Strip markdown code fences if the model adds them anyway
    raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    data = json.loads(raw)
    return {
        "route":          route,
        "departure_time": departure_time,
        "dead_zones":     data,
        "_source":        "llm_predict",
    }


def _is_lincoln_tunnel_stub(data: dict) -> bool:
    """Return True if the response looks like the known hardcoded Lincoln Tunnel stub."""
    try:
        zones = data["dead_zones"]["dead_zones"]
        if not zones:
            return False
        first = zones[0]["location"]
        # Lincoln Tunnel Mid is at ~40.762, -74.031
        return abs(first.get("lat", 0) - 40.7621) < 0.01 and abs(first.get("lon", 0) - (-74.0312)) < 0.01
    except Exception:
        return False


def _hardcoded_fallback(route: str, departure_time: str) -> dict:
    """Last-resort static response when neither Agent 1 nor the LLM is available."""
    return {
        "route":          route,
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
        "_source": "hardcoded_fallback",
    }


@tool(name="agent1_predict")
async def predict(route: str, departure_time: str) -> dict:
    """Predict dead zones for a route. Tries Agent 1 first, then LLM fallback."""
    payload = {"route": route, "departure_time": departure_time}

    # 1. Try the original Agent 1 service — but only trust it if it returns zones
    #    whose coordinates actually match the requested route (not the Lincoln Tunnel stub).
    if _AGENT1_URL and _AGENT1_URL != "http://localhost:8001":
        try:
            async with httpx.AsyncClient(timeout=15.0) as http:
                resp = await http.post(f"{_AGENT1_URL}/predict", json=payload)
                resp.raise_for_status()
                data = resp.json()

            # Sanity-check: if the external service returned the known hardcoded Lincoln
            # Tunnel stub (lat≈40.76, lng≈-74.03) for a route that has nothing to do with
            # NJ/NY, discard the response and fall through to LLM prediction instead.
            if _is_lincoln_tunnel_stub(data) and "newark" not in route.lower() \
                    and "manhattan" not in route.lower() and "new jersey" not in route.lower() \
                    and "lincoln" not in route.lower():
                print(f"[agent1] External service returned NJ stub for '{route}'; using LLM fallback")
                raise ValueError("stub response for non-NJ route")

            data.setdefault("_source", "agent1")
            try:
                LLMObs.annotate(
                    input_data=payload,
                    output_data={"dead_zones_count": _count_zones(data)},
                    metadata={"backend": "agent1", "url": _AGENT1_URL},
                    tags={"tool": "agent1_predict"},
                )
            except Exception:
                pass
            return data
        except Exception as e:
            print(f"[agent1] Agent 1 skipped ({e}); using LLM fallback")

    # 2. LLM-based prediction (works for any route worldwide)
    try:
        data = await _llm_predict(route, departure_time)
        try:
            LLMObs.annotate(
                input_data=payload,
                output_data={"dead_zones_count": _count_zones(data)},
                metadata={"backend": "llm_predict"},
                tags={"tool": "agent1_predict"},
            )
        except Exception:
            pass
        return data
    except Exception as e:
        print(f"[agent1] LLM prediction failed ({e}); using hardcoded fallback")
        return _hardcoded_fallback(route, departure_time)


def _count_zones(resp: dict) -> int:
    try:
        return len(resp["dead_zones"]["dead_zones"])
    except Exception:
        return 0


def normalize_zones(resp: dict) -> list[dict]:
    """Flatten the response into a list of {id, lat, lng, description, ...} dicts."""
    out: list[dict] = []
    try:
        zones = resp["dead_zones"]["dead_zones"]
    except Exception:
        return out
    for i, z in enumerate(zones):
        loc = z.get("location", {})
        out.append({
            "id":               f"dz_{i:02d}_{(loc.get('description') or '').lower().replace(' ', '_')[:24]}",
            "lat":              loc.get("lat"),
            "lng":              loc.get("lon"),
            "description":      loc.get("description", f"Zone {i}"),
            "start_time":       z.get("start_time"),
            "duration_minutes": z.get("duration_minutes"),
            "severity":         z.get("severity"),
        })
    return out
