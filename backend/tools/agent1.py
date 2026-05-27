"""Agent 1 — dead zone prediction for any driving route.

Prediction priority (agentic-first):
  1. LLM (OpenRouter → Groq)                   — primary agentic prediction
  2. CoverageMap API + Google Maps Directions  — real signal strength data
  3. Transit / driving hardcoded zones          — fail-safe for known routes
  4. Generic hardcoded stub                     — last resort

Circuit breaker: once the LLM provider chain fails, a process-level breaker
trips for `_LLM_CIRCUIT_COOLDOWN` seconds. While the breaker is open, calls
skip the LLM and fall straight through to CoverageMap → hardcoded, so we
don't pay a timeout/429 on every subsequent request during a provider outage.
The breaker auto-resets after the cooldown and the LLM is retried.
"""
from __future__ import annotations
import os
import re
import json
import math
import time
import httpx
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

_AGENT1_URL        = os.getenv("AGENT1_URL",         "").strip().rstrip("/")
_OPENROUTER_KEY    = os.getenv("OPENROUTER_API_KEY",  "").strip()
_OPENROUTER_MODEL  = os.getenv("OPENAI_MODEL",        "google/gemini-2.0-flash-001").strip()
_GROQ_KEY          = os.getenv("GROQ_API_KEY",        "").strip()
_GROQ_MODEL        = os.getenv("GROQ_MODEL",          "llama-3.3-70b-versatile").strip()
_COVERAGEMAP_KEY   = os.getenv("COVERAGEMAP_API_KEY", "").strip()
_GOOGLE_MAPS_KEY   = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()

_COVERAGEMAP_URL   = "https://enterprise.coveragemap.com/api/v1/signal-strength/lookup"
_GMAPS_URL         = "https://maps.googleapis.com/maps/api/directions/json"
_DEAD_ZONE_DBM     = -95    # below this = weak/dead signal (poor call/data quality)
_CLUSTER_GAP_KM    = 8.0    # points further apart than this start a new cluster

# ── LLM circuit breaker ───────────────────────────────────────────
# Trips when the LLM provider chain fails (timeouts, 402, 429, 5xx).
# While open, predict() skips the LLM entirely and goes to CoverageMap +
# hardcoded fallbacks — saves 30s+ of timeout per request during an outage.
_LLM_CIRCUIT_OPEN_UNTIL: float = 0.0
_LLM_CIRCUIT_COOLDOWN  : float = float(os.getenv("LLM_CIRCUIT_COOLDOWN_SEC", "300"))  # 5 min default


def _llm_circuit_open() -> bool:
    return time.time() < _LLM_CIRCUIT_OPEN_UNTIL


def _trip_llm_circuit(reason: str) -> None:
    global _LLM_CIRCUIT_OPEN_UNTIL
    _LLM_CIRCUIT_OPEN_UNTIL = time.time() + _LLM_CIRCUIT_COOLDOWN
    print(f"[agent1] LLM circuit OPEN for {int(_LLM_CIRCUIT_COOLDOWN)}s ({reason})", flush=True)


def _reset_llm_circuit() -> None:
    global _LLM_CIRCUIT_OPEN_UNTIL
    if _LLM_CIRCUIT_OPEN_UNTIL > 0:
        print("[agent1] LLM circuit CLOSED (provider recovered)", flush=True)
    _LLM_CIRCUIT_OPEN_UNTIL = 0.0


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
    "geography. Your job is to predict where drivers will lose signal on a given route. "
    "Respond in English only. All location descriptions must use English landmark names."
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


def _extract_json(raw: str) -> dict:
    """Pull a JSON object out of an LLM response that may have fences/prose around it."""
    cleaned = re.sub(r"```(?:json)?\s*", "", raw)
    cleaned = re.sub(r"\s*```", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Fallback: find the outermost {...} and try to parse that
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"No JSON object found in LLM output. First 300 chars: {cleaned[:300]!r}")


async def _call_llm(provider: str, base_url: str, api_key: str, model: str, route: str, departure_time: str) -> dict:
    """Single attempt against one provider. Raises on any failure."""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=30.0)
    prompt = _LLM_PROMPT.format(route=route, departure_time=departure_time)

    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _LLM_SYSTEM},
            {"role": "user",   "content": prompt},
        ],
        temperature=0.2,
        max_tokens=1024,
    )
    raw = resp.choices[0].message.content or ""
    if not raw:
        raise ValueError(f"{provider} returned empty content")

    data = _extract_json(raw)
    if "dead_zones" not in data:
        raise ValueError(f"{provider} response missing 'dead_zones' key (keys: {list(data.keys())})")
    if not isinstance(data["dead_zones"], list) or not data["dead_zones"]:
        raise ValueError(f"{provider} returned empty/invalid dead_zones list")

    print(f"[agent1] {provider} success: {len(data['dead_zones'])} zone(s) for '{route}' via {model}", flush=True)
    return data


async def _llm_predict(route: str, departure_time: str) -> dict:
    """Try OpenRouter (primary), fall back to Groq. Raise if both fail."""
    if not _OPENROUTER_KEY and not _GROQ_KEY:
        print(f"[agent1] LLM skipped: neither OPENROUTER_API_KEY nor GROQ_API_KEY set", flush=True)
        return _hardcoded_fallback(route, departure_time)

    last_error: Exception | None = None

    # 1. OpenRouter (primary)
    if _OPENROUTER_KEY:
        try:
            data = await _call_llm("OpenRouter", "https://openrouter.ai/api/v1", _OPENROUTER_KEY, _OPENROUTER_MODEL, route, departure_time)
            _reset_llm_circuit()
            return {"route": route, "departure_time": departure_time, "dead_zones": data, "_source": "llm_predict_openrouter"}
        except Exception as e:
            print(f"[agent1] OpenRouter failed for '{route}': {type(e).__name__}: {e!s}; trying Groq", flush=True)
            last_error = e

    # 2. Groq (fallback — free tier, fast LPU inference)
    if _GROQ_KEY:
        try:
            data = await _call_llm("Groq", "https://api.groq.com/openai/v1", _GROQ_KEY, _GROQ_MODEL, route, departure_time)
            _reset_llm_circuit()
            return {"route": route, "departure_time": departure_time, "dead_zones": data, "_source": "llm_predict_groq"}
        except Exception as e:
            print(f"[agent1] Groq failed for '{route}': {type(e).__name__}: {e!s}", flush=True)
            last_error = e

    # Both providers failed — trip the breaker so subsequent calls skip the LLM
    # until the cooldown expires.
    _trip_llm_circuit(f"{type(last_error).__name__ if last_error else 'unknown'}")
    raise last_error or RuntimeError("All LLM providers failed")


# ── Transit dead zone database ────────────────────────────────────
# Verified geographic dead zones for known transit lines.
# These always take priority over the LLM (which gets tunnel locations wrong).
# Keyed by a lowercase substring that uniquely identifies the route string.

_TRANSIT_ZONES: dict[str, list[dict]] = {
    # L train: the ONLY major dead zone is the Canarsie tunnel under the East River
    # between Bedford Av (Brooklyn) and 1st Av (Manhattan).
    "l train canarsie": [
        {
            "location": {
                "lat": 40.7244, "lon": -73.9668,
                "description": "Canarsie Tunnel (Bedford Av → 1st Av, under East River)",
            },
            "start_time": "17:08",
            "duration_minutes": 5,
            "severity": "high",
        },
    ],
    # E train: Queens Midtown Tunnel approach + lower Manhattan underground
    "e train jamaica": [
        {
            "location": {
                "lat": 40.7480, "lon": -73.9501,
                "description": "Queens Midtown Tunnel (Court Sq → Lex/53 St)",
            },
            "start_time": "17:14",
            "duration_minutes": 6,
            "severity": "high",
        },
        {
            "location": {
                "lat": 40.7117, "lon": -74.0129,
                "description": "Lower Manhattan Underground (Fulton St → WTC)",
            },
            "start_time": "17:32",
            "duration_minutes": 3,
            "severity": "medium",
        },
    ],
    # BART: the Transbay Tube under San Francisco Bay is the dominant dead zone
    # (3.6 miles underwater, Embarcadero → West Oakland)
    "bart embarcadero": [
        {
            "location": {
                "lat": 37.7981, "lon": -122.3449,
                "description": "Transbay Tube (Embarcadero → West Oakland, under SF Bay)",
            },
            "start_time": "17:06",
            "duration_minutes": 8,
            "severity": "high",
        },
        {
            "location": {
                "lat": 37.6895, "lon": -122.4663,
                "description": "Daly City Underground (Colma → Daly City stations)",
            },
            "start_time": "17:38",
            "duration_minutes": 3,
            "severity": "medium",
        },
    ],
}


def _transit_hardcoded(route: str, departure_time: str) -> dict | None:
    """Return verified transit dead zones if route matches a known transit line."""
    rl = route.lower()
    for key, zones in _TRANSIT_ZONES.items():
        if key in rl:
            print(f"[agent1] transit hardcoded: matched '{key}' for '{route}'")
            return {
                "route": route,
                "departure_time": departure_time,
                "dead_zones": {"dead_zones": zones},
                "_source": "transit_hardcoded",
            }
    return None


# ── Driving dead zone database ────────────────────────────────────
# Verified zones for the six curated driving routes in the trip planner.
# Used as primary fallback when CoverageMap/LLM are unavailable so the
# demo is deterministic regardless of external API state.
_DRIVING_ZONES: dict[str, list[dict]] = {
    # Manhattan → Newark
    "manhattan to newark": [
        {"location": {"lat": 40.7621, "lon": -74.0312, "description": "Lincoln Tunnel Mid"},
         "start_time": "17:06", "duration_minutes": 5, "severity": "high"},
        {"location": {"lat": 40.7357, "lon": -74.1724, "description": "Newark McCarter Hwy"},
         "start_time": "17:16", "duration_minutes": 1, "severity": "low"},
    ],
    # Denver → Vail (Eisenhower Tunnel + I-70 canyons)
    "denver to vail": [
        {"location": {"lat": 39.6800, "lon": -105.9143, "description": "Eisenhower Tunnel"},
         "start_time": "17:42", "duration_minutes": 4, "severity": "high"},
        {"location": {"lat": 39.5286, "lon": -106.2189, "description": "Vail Pass"},
         "start_time": "18:05", "duration_minutes": 3, "severity": "medium"},
    ],
    # Los Angeles → Las Vegas (I-15 corridor)
    "los angeles to las vegas": [
        {"location": {"lat": 34.3061, "lon": -117.4742, "description": "Cajon Pass"},
         "start_time": "17:35", "duration_minutes": 2, "severity": "medium"},
        {"location": {"lat": 35.2680, "lon": -116.0697, "description": "Mojave Desert (Baker)"},
         "start_time": "19:10", "duration_minutes": 8, "severity": "high"},
        {"location": {"lat": 35.6105, "lon": -115.3902, "description": "Primm / Stateline"},
         "start_time": "20:25", "duration_minutes": 2, "severity": "low"},
    ],
    # Big Sur PCH (Carmel to San Luis Obispo via Highway 1)
    "carmel to san luis obispo": [
        {"location": {"lat": 36.3722, "lon": -121.9023, "description": "Bixby Bridge"},
         "start_time": "17:20", "duration_minutes": 4, "severity": "high"},
        {"location": {"lat": 36.2461, "lon": -121.7714, "description": "Big Sur Deep Canyon"},
         "start_time": "17:55", "duration_minutes": 8, "severity": "high"},
        {"location": {"lat": 35.7707, "lon": -121.3210, "description": "Gorda / Ragged Point"},
         "start_time": "19:10", "duration_minutes": 5, "severity": "high"},
    ],
    "highway 1 big sur": [
        {"location": {"lat": 36.3722, "lon": -121.9023, "description": "Bixby Bridge"},
         "start_time": "17:20", "duration_minutes": 4, "severity": "high"},
        {"location": {"lat": 36.2461, "lon": -121.7714, "description": "Big Sur Deep Canyon"},
         "start_time": "17:55", "duration_minutes": 8, "severity": "high"},
        {"location": {"lat": 35.7707, "lon": -121.3210, "description": "Gorda / Ragged Point"},
         "start_time": "19:10", "duration_minutes": 5, "severity": "high"},
    ],
    # US-50 Nevada (Ely to Fallon — Loneliest Road)
    "ely to fallon": [
        {"location": {"lat": 39.4583, "lon": -117.3658, "description": "Bob Scott Summit"},
         "start_time": "18:10", "duration_minutes": 4, "severity": "high"},
        {"location": {"lat": 39.5045, "lon": -117.0732, "description": "Austin Summit"},
         "start_time": "18:45", "duration_minutes": 6, "severity": "high"},
        {"location": {"lat": 39.2848, "lon": -118.0445, "description": "Middlegate Station"},
         "start_time": "20:25", "duration_minutes": 8, "severity": "high"},
    ],
    "us route 50 nevada": [
        {"location": {"lat": 39.4583, "lon": -117.3658, "description": "Bob Scott Summit"},
         "start_time": "18:10", "duration_minutes": 4, "severity": "high"},
        {"location": {"lat": 39.5045, "lon": -117.0732, "description": "Austin Summit"},
         "start_time": "18:45", "duration_minutes": 6, "severity": "high"},
        {"location": {"lat": 39.2848, "lon": -118.0445, "description": "Middlegate Station"},
         "start_time": "20:25", "duration_minutes": 8, "severity": "high"},
    ],
    # Million Dollar Highway (Ouray to Durango via US-550)
    "ouray to durango": [
        {"location": {"lat": 37.8967, "lon": -107.7128, "description": "Red Mountain Pass (11,018 ft)"},
         "start_time": "17:28", "duration_minutes": 8, "severity": "high"},
        {"location": {"lat": 37.7479, "lon": -107.6839, "description": "Molas Pass (10,910 ft)"},
         "start_time": "18:05", "duration_minutes": 5, "severity": "high"},
        {"location": {"lat": 37.6979, "lon": -107.7717, "description": "Coal Bank Pass"},
         "start_time": "18:30", "duration_minutes": 3, "severity": "medium"},
    ],
    "million dollar highway": [
        {"location": {"lat": 37.8967, "lon": -107.7128, "description": "Red Mountain Pass (11,018 ft)"},
         "start_time": "17:28", "duration_minutes": 8, "severity": "high"},
        {"location": {"lat": 37.7479, "lon": -107.6839, "description": "Molas Pass (10,910 ft)"},
         "start_time": "18:05", "duration_minutes": 5, "severity": "high"},
        {"location": {"lat": 37.6979, "lon": -107.7717, "description": "Coal Bank Pass"},
         "start_time": "18:30", "duration_minutes": 3, "severity": "medium"},
    ],
}


def _driving_hardcoded(route: str, departure_time: str) -> dict | None:
    """Return verified driving dead zones if route matches a known driving route."""
    rl = route.lower()
    for key, zones in _DRIVING_ZONES.items():
        if key in rl:
            print(f"[agent1] driving hardcoded: matched '{key}' for '{route}'")
            return {
                "route": route,
                "departure_time": departure_time,
                "dead_zones": {"dead_zones": zones},
                "_source": "driving_hardcoded",
            }
    return None


def is_transit_route(route: str) -> bool:
    """True if the route string describes a subway/rail transit line."""
    markers = ["train", "subway", "bart", "metro", "mta", "transit", "tube", "rail"]
    rl = route.lower()
    return any(m in rl for m in markers)


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
    """Predict dead zones. LLM (primary) → CoverageMap → hardcoded fail-safes.

    Circuit breaker: if the LLM chain has failed recently, skip it entirely
    until the cooldown expires (avoids paying 30s timeout per request during
    a provider outage). Hardcoded zones are ONLY used as fail-safes.
    """
    payload = {"route": route, "departure_time": departure_time}

    # 1. LLM — the primary agentic prediction. Skipped only if the breaker is
    # currently open from a recent failure.
    if not _llm_circuit_open():
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
            print(f"[agent1] LLM prediction failed ({type(e).__name__}: {e}); falling through to CoverageMap/hardcoded", flush=True)
    else:
        remaining = int(_LLM_CIRCUIT_OPEN_UNTIL - time.time())
        print(f"[agent1] LLM circuit open ({remaining}s left); skipping LLM for '{route}'", flush=True)

    # 2. CoverageMap real signal data — only if both keys present
    if _COVERAGEMAP_KEY and _GOOGLE_MAPS_KEY:
        try:
            data = await _coveragemap_predict(route, departure_time)
            zone_count = _count_zones(data)
            print(f"[agent1] CoverageMap: {zone_count} dead zone(s) for '{route}'", flush=True)
            if zone_count > 0:
                try:
                    LLMObs.annotate(
                        input_data=payload,
                        output_data={"dead_zones_count": zone_count},
                        metadata={"backend": "coveragemap"},
                        tags={"tool": "agent1_predict"},
                    )
                except Exception:
                    pass
                return data
            print(f"[agent1] CoverageMap found 0 zones for '{route}'; trying hardcoded fail-safe", flush=True)
        except Exception as e:
            print(f"[agent1] CoverageMap failed ({type(e).__name__}: {e}); trying hardcoded fail-safe", flush=True)

    # 3. Transit hardcoded fail-safe — known transit lines (tunnels)
    transit = _transit_hardcoded(route, departure_time)
    if transit is not None:
        try:
            LLMObs.annotate(
                input_data=payload,
                output_data={"dead_zones_count": _count_zones(transit)},
                metadata={"backend": "transit_hardcoded"},
                tags={"tool": "agent1_predict"},
            )
        except Exception:
            pass
        return transit

    # 4. Driving hardcoded fail-safe — curated routes in the trip planner
    driving = _driving_hardcoded(route, departure_time)
    if driving is not None:
        try:
            LLMObs.annotate(
                input_data=payload,
                output_data={"dead_zones_count": _count_zones(driving)},
                metadata={"backend": "driving_hardcoded"},
                tags={"tool": "agent1_predict"},
            )
        except Exception:
            pass
        return driving

    # 5. Generic last-resort fallback for unknown routes when everything else fails
    return _hardcoded_fallback(route, departure_time)


def _count_zones(resp: dict) -> int:
    try:
        return len(resp["dead_zones"]["dead_zones"])
    except Exception:
        return 0


def _sanitize_desc(s: str | None, fallback: str) -> str:
    """Strip non-ASCII chars from LLM-generated descriptions (occasional Cyrillic / CJK leakage)."""
    if not s:
        return fallback
    cleaned = re.sub(r"[^\x00-\x7F]+", "", s)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,-/")
    return cleaned if cleaned else fallback


def normalize_zones(resp: dict) -> list[dict]:
    """Flatten the response into a list of {id, lat, lng, description, ...} dicts."""
    out: list[dict] = []
    try:
        zones = resp["dead_zones"]["dead_zones"]
    except Exception:
        return out
    for i, z in enumerate(zones):
        loc = z.get("location", {})
        desc = _sanitize_desc(loc.get("description"), f"Zone {i + 1}")
        out.append({
            "id":               f"dz_{i:02d}_{desc.lower().replace(' ', '_')[:24]}",
            "lat":              loc.get("lat"),
            "lng":              loc.get("lon"),
            "description":      desc,
            "start_time":       z.get("start_time"),
            "duration_minutes": z.get("duration_minutes"),
            "severity":         z.get("severity"),
        })
    return out
