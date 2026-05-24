"""Agent 1 — dead zone prediction for any driving route.

Prediction priority:
  1. CoverageMap API + Google Maps Directions  — real signal strength data
  2. LLM fallback (OpenRouter/Gemini)          — geographic knowledge
  3. Hardcoded stub                             — last resort only

CoverageMap queries T-Mobile signal strength at evenly-spaced waypoints
along the actual road route. Points below -105 dBm are flagged as dead zones
and clustered into segments.
"""
from __future__ import annotations
import os
import re
import json
import math
import httpx
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

_AGENT1_URL        = os.getenv("AGENT1_URL",         "").strip().rstrip("/")
_OPENROUTER_KEY    = os.getenv("OPENROUTER_API_KEY",  "").strip()
_COVERAGEMAP_KEY   = os.getenv("COVERAGEMAP_API_KEY", "").strip()
_GOOGLE_MAPS_KEY   = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()

_COVERAGEMAP_URL   = "https://enterprise.coveragemap.com/api/v1/signal-strength/lookup"
_GMAPS_URL         = "https://maps.googleapis.com/maps/api/directions/json"
_DEAD_ZONE_DBM     = -105   # below this = dead zone
_CLUSTER_GAP_KM    = 8.0    # points further apart than this start a new cluster


# ── Real data: CoverageMap + Google Maps ──────────────────────────

async def _get_waypoints(origin: str, destination: str, num_points: int = 30) -> list[dict]:
    """Decode the overview polyline from Google Maps Directions into lat/lng waypoints."""
    import polyline as poly_lib
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            _GMAPS_URL,
            params={"origin": origin, "destination": destination, "key": _GOOGLE_MAPS_KEY},
        )
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") != "OK":
        raise ValueError(f"Google Maps error: {data.get('status')} — {data.get('error_message', '')}")

    encoded = data["routes"][0]["overview_polyline"]["points"]
    coords  = poly_lib.decode(encoded)
    step    = max(1, len(coords) // num_points)
    sampled = coords[::step][:num_points]
    return [{"lat": lat, "lng": lng} for lat, lng in sampled]


async def _check_signal(waypoints: list[dict]) -> list[dict]:
    """Query CoverageMap for T-Mobile signal at each waypoint. Returns dead zone points."""
    dead: list[dict] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for wp in waypoints:
            try:
                resp = await client.get(
                    _COVERAGEMAP_URL,
                    headers={"Authorization": f"Bearer {_COVERAGEMAP_KEY}"},
                    params={"latitude": wp["lat"], "longitude": wp["lng"], "providers": "TMO"},
                )
                resp.raise_for_status()
                results = resp.json()
                result  = results[0] if results else {}
                dbm     = result.get("signal", {}).get("signal")
                if dbm is not None and dbm < _DEAD_ZONE_DBM:
                    dead.append({**wp, "signal_dbm": dbm})
            except Exception:
                pass  # skip failed waypoints; don't abort the whole route
    return dead


def _haversine_km(a: dict, b: dict) -> float:
    R = 6371.0
    dlat = math.radians(b["lat"] - a["lat"])
    dlng = math.radians(b["lng"] - a["lng"])
    h = math.sin(dlat / 2) ** 2 + math.cos(math.radians(a["lat"])) * math.cos(math.radians(b["lat"])) * math.sin(dlng / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _cluster_to_zones(dead_points: list[dict], departure_time: str) -> list[dict]:
    """Group nearby dead zone points into dead zone objects."""
    if not dead_points:
        return []

    clusters: list[list[dict]] = []
    current = [dead_points[0]]
    for pt in dead_points[1:]:
        if _haversine_km(current[-1], pt) <= _CLUSTER_GAP_KM:
            current.append(pt)
        else:
            clusters.append(current)
            current = [pt]
    clusters.append(current)

    zones = []
    for cluster in clusters:
        lat = sum(p["lat"] for p in cluster) / len(cluster)
        lon = sum(p["lng"] for p in cluster) / len(cluster)
        avg_dbm  = sum(p.get("signal_dbm", -110) for p in cluster) / len(cluster)
        dur_min  = max(1, min(10, len(cluster) * 2))
        severity = "high" if avg_dbm < -115 else "medium" if avg_dbm < -110 else "low"
        zones.append({
            "location": {"lat": lat, "lon": lon, "description": f"Low signal zone ({avg_dbm:.0f} dBm)"},
            "start_time":       departure_time,
            "duration_minutes": dur_min,
            "severity":         severity,
        })
    return zones


async def _coveragemap_predict(route: str, departure_time: str) -> dict:
    """Real dead zone prediction: Google Maps waypoints → CoverageMap signal check."""
    # Parse "Origin to Destination"
    parts = re.split(r"\s+to\s+", route, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        raise ValueError(f"Cannot parse route '{route}' — expected 'Origin to Destination'")
    origin, destination = parts[0].strip(), parts[1].strip()

    waypoints  = await _get_waypoints(origin, destination, num_points=30)
    dead_pts   = await _check_signal(waypoints)
    zones      = _cluster_to_zones(dead_pts, departure_time)

    # If CoverageMap returned no dead zones, still return an empty list
    # (the LLM fallback handles zero-zone routes by fabricating one)
    return {
        "route":          route,
        "departure_time": departure_time,
        "dead_zones":     {"dead_zones": zones},
        "_source":        "coveragemap",
    }


# ── LLM fallback ─────────────────────────────────────────────────

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
    if not _OPENROUTER_KEY:
        return _hardcoded_fallback(route, departure_time)
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=_OPENROUTER_KEY, base_url="https://openrouter.ai/api/v1")
    prompt = _LLM_PROMPT.format(route=route, departure_time=departure_time)
    resp = await client.chat.completions.create(
        model="google/gemini-2.0-flash-001",
        messages=[{"role": "system", "content": _LLM_SYSTEM}, {"role": "user", "content": prompt}],
        temperature=0.2,
    )
    raw = resp.choices[0].message.content or ""
    raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    data = json.loads(raw)
    return {"route": route, "departure_time": departure_time, "dead_zones": data, "_source": "llm_predict"}


def _is_lincoln_tunnel_stub(data: dict) -> bool:
    try:
        first = data["dead_zones"]["dead_zones"][0]["location"]
        return abs(first.get("lat", 0) - 40.7621) < 0.01 and abs(first.get("lon", 0) - (-74.0312)) < 0.01
    except Exception:
        return False


def _hardcoded_fallback(route: str, departure_time: str) -> dict:
    return {
        "route": route, "departure_time": departure_time,
        "dead_zones": {"dead_zones": [
            {"location": {"lat": 40.7621, "lon": -74.0312, "description": "Lincoln Tunnel Mid"},
             "start_time": "17:06", "duration_minutes": 5, "severity": "high"},
            {"location": {"lat": 40.7357, "lon": -74.1724, "description": "Newark McCarter Hwy"},
             "start_time": "17:16", "duration_minutes": 1, "severity": "low"},
        ]},
        "_source": "hardcoded_fallback",
    }


# ── Public API ────────────────────────────────────────────────────

@tool(name="agent1_predict")
async def predict(route: str, departure_time: str) -> dict:
    """Predict dead zones. CoverageMap (real) → LLM (fallback) → hardcoded (last resort)."""
    payload = {"route": route, "departure_time": departure_time}

    # 1. Real signal data via CoverageMap + Google Maps
    if _COVERAGEMAP_KEY and _GOOGLE_MAPS_KEY:
        try:
            data = await _coveragemap_predict(route, departure_time)
            print(f"[agent1] CoverageMap: {_count_zones(data)} dead zone(s) for '{route}'")
            try:
                LLMObs.annotate(
                    input_data=payload,
                    output_data={"dead_zones_count": _count_zones(data)},
                    metadata={"backend": "coveragemap"},
                    tags={"tool": "agent1_predict"},
                )
            except Exception:
                pass
            return data
        except Exception as e:
            print(f"[agent1] CoverageMap failed ({e}); falling back to LLM")

    # 2. LLM geographic knowledge fallback
    try:
        data = await _llm_predict(route, departure_time)
        print(f"[agent1] LLM: {_count_zones(data)} dead zone(s) for '{route}'")
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
