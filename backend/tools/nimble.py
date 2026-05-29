"""Nimble web-search wrapper. Falls back to LLM-generated route-specific content when the
Nimble API key is absent (demo mode). The LLM stub uses the full search query to produce
content that is specific to the actual route and dead-zone location — never hardcoded to
a single geography."""
from __future__ import annotations
import os
import re
import json
import asyncio
import httpx
from bus import emit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool
from tools import llm_circuit

NIMBLE_URL = "https://api.webit.live/api/v1/realtime/serp"
_API_KEY        = os.getenv("NIMBLE_API_KEY",    "").strip()
_OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
_OPENROUTER_MODEL = os.getenv("OPENAI_MODEL", "google/gemini-2.0-flash-001").strip()
_GROQ_KEY       = os.getenv("GROQ_API_KEY", "").strip()
_GROQ_MODEL     = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
_CEREBRAS_KEY   = os.getenv("CEREBRAS_API_KEY", "").strip()
_CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "llama-3.3-70b").strip()

# Short per-request timeout so a dead/queued provider can't drag the
# nimble stub. Matches orchestrator's 5s default.
_LLM_TIMEOUT_SEC = float(os.getenv("LLM_TIMEOUT_SEC", "5"))

# Pick provider — OpenRouter primary, Groq fallback, Cerebras final.
if _OPENROUTER_KEY:
    _LLM_PROVIDER, _LLM_KEY, _LLM_BASE_URL, _LLM_MODEL = "openrouter", _OPENROUTER_KEY, "https://openrouter.ai/api/v1", _OPENROUTER_MODEL
elif _GROQ_KEY:
    _LLM_PROVIDER, _LLM_KEY, _LLM_BASE_URL, _LLM_MODEL = "groq", _GROQ_KEY, "https://api.groq.com/openai/v1", _GROQ_MODEL
elif _CEREBRAS_KEY:
    _LLM_PROVIDER, _LLM_KEY, _LLM_BASE_URL, _LLM_MODEL = "cerebras", _CEREBRAS_KEY, "https://api.cerebras.ai/v1", _CEREBRAS_MODEL
else:
    _LLM_PROVIDER, _LLM_KEY, _LLM_BASE_URL, _LLM_MODEL = "", "", "", ""

# Back-compat
_MODEL = _LLM_MODEL

_URL_CHECK_TIMEOUT = 3.0   # seconds per URL reachability check

# Byte patterns that indicate a soft 404 (server says 200 but content says "not found").
# Checked against the first ~512 bytes of the response body, lowercased.
_SOFT_404_PATTERNS = (
    b"404 not found",
    b"page not found",
    b"page does not exist",
    b"content not found",
    b"this page could not be found",
    b"the page you are looking for",
    b"no longer available",
    b"article not found",
)


async def _is_reachable(url: str) -> bool:
    """Return True only when the URL serves real, accessible content.

    Strategy
    --------
    1. HEAD request — cheap, no body downloaded.
       • 2xx  →  reachable ✓
       • 4xx / 5xx (except 405 "HEAD not allowed")  →  unreachable immediately;
         no point retrying with GET when the server already said the page is gone.
       • 405 or connection error  →  fall through to GET.

    2. Streaming GET with a Range header — reads only the first 512 bytes.
       • Non-2xx status  →  unreachable.
       • 2xx but body starts with a known soft-404 phrase  →  unreachable.
         (Catches sites that return HTTP 200 for "Page Not Found" pages.)
    """
    if not url or not url.startswith("http"):
        return False
    try:
        async with httpx.AsyncClient(
            timeout=_URL_CHECK_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; DeadZonePackBuilder/1.0)"},
        ) as client:
            try:
                r = await client.head(url)
                if 200 <= r.status_code < 300:
                    return True
                if r.status_code != 405:
                    # Definitive failure (404, 403, 410, 5xx …) — skip GET
                    return False
            except Exception:
                pass  # HEAD timed out or connection refused — try GET

            # HEAD returned 405 ("not allowed") or failed — use a minimal GET
            async with client.stream("GET", url, headers={"Range": "bytes=0-511"}) as r:
                if not (200 <= r.status_code < 300):
                    return False
                # Read the first chunk to detect soft-404 pages
                chunk = b""
                async for c in r.aiter_bytes(512):
                    chunk = c
                    break
                return not any(pat in chunk.lower() for pat in _SOFT_404_PATTERNS)
    except Exception:
        return False


async def _validate_sources(sources: list[dict]) -> list[dict]:
    """Check all source URLs in parallel.

    Each source gets a ``reachable`` boolean. Reachable sources are returned
    first so the pack leads with working links; unreachable ones are kept at
    the end so senso.py can still render title + snippet as plain text.
    Result is capped at 4 entries total.
    """
    if not sources:
        return sources
    checks = await asyncio.gather(*[_is_reachable(s.get("url", "")) for s in sources])
    for source, ok in zip(sources, checks):
        source["reachable"] = bool(ok)
    reachable   = [s for s in sources if s["reachable"]]
    unreachable = [s for s in sources if not s["reachable"]]
    # Reachable sources first; keep unreachable ones so their text/snippet is still readable
    return (reachable + unreachable)[:4]


_LLM_SYSTEM = (
    "You are a web-search result simulator. "
    "Your job is to return realistic, location-specific search results for the query given. "
    "The content MUST be relevant to the exact location and topic in the query. "
    "Never invent content about unrelated places."
)

_LLM_PROMPT = """\
Simulate realistic web search results for this query:

Query: {query}

Return ONLY valid JSON — no markdown fences, no explanation. Use this exact schema:
{{"summary": "<2-3 sentence factual summary specific to the location/route in the query>",
  "sources": [
    {{"url": "<realistic authoritative URL for this region>",
      "title": "<realistic page title>",
      "snippet": "<1-2 sentence excerpt relevant to the query>"}},
    {{"url": "<realistic authoritative URL for this region>",
      "title": "<realistic page title>",
      "snippet": "<1-2 sentence excerpt relevant to the query>"}},
    {{"url": "<realistic authoritative URL for this region>",
      "title": "<realistic page title>",
      "snippet": "<1-2 sentence excerpt relevant to the query>"}},
    {{"url": "<realistic authoritative URL for this region>",
      "title": "<realistic page title>",
      "snippet": "<1-2 sentence excerpt relevant to the query>"}}
  ]
}}

Rules:
- The summary and snippets MUST be specific to the location and route mentioned in the query.
- Use realistic government, news, or traffic URLs for the relevant US state/region.
- Do NOT mention the Adirondacks, Lake George, I-87, or NY unless the query explicitly refers to those.
- For emergency/rescue queries: include real county sheriff phone numbers and SAR team URLs for the region.
- For mountain/pass weather queries: include elevation-specific forecast data and storm alert agencies (NWS, CAIC, etc.).
- For road closure/CDOT queries: include state DOT URLs (cotrip.org, nevadadot.com, caltrans.ca.gov, etc.) and live camera links.
- For gas/fuel/services queries: include last services before the dead zone, with realistic mileage distances.
- For transit queries: include the real agency URL (mta.info, bart.gov, transitapp.com) and service alert language.
- Prioritize actionable, safety-relevant content over general interest articles.
"""


async def _call_llm_with_fallback(query: str):
    """Try OpenRouter, then Groq. Returns (raw_content, provider_name) or raises."""
    from openai import AsyncOpenAI
    messages = [
        {"role": "system", "content": _LLM_SYSTEM},
        {"role": "user",   "content": _LLM_PROMPT.format(query=query)},
    ]
    last_error: Exception | None = None

    if _OPENROUTER_KEY and not llm_circuit.is_open("openrouter"):
        try:
            c = AsyncOpenAI(api_key=_OPENROUTER_KEY, base_url="https://openrouter.ai/api/v1", timeout=_LLM_TIMEOUT_SEC, max_retries=0)
            r = await c.chat.completions.create(
                model=_OPENROUTER_MODEL, messages=messages, temperature=0.3, max_tokens=1024,
            )
            llm_circuit.reset("openrouter")
            return (r.choices[0].message.content or ""), "openrouter"
        except Exception as e:
            print(f"[nimble] OpenRouter stub failed: {type(e).__name__}: {str(e)[:160]}; trying Groq", flush=True)
            llm_circuit.classify_and_trip("openrouter", e)
            last_error = e
    elif _OPENROUTER_KEY:
        print(f"[nimble] OpenRouter circuit open ({llm_circuit.seconds_remaining('openrouter')}s); skipping", flush=True)

    if _GROQ_KEY and not llm_circuit.is_open("groq"):
        try:
            c = AsyncOpenAI(api_key=_GROQ_KEY, base_url="https://api.groq.com/openai/v1", timeout=_LLM_TIMEOUT_SEC, max_retries=0)
            r = await c.chat.completions.create(
                model=_GROQ_MODEL, messages=messages, temperature=0.3, max_tokens=1024,
            )
            llm_circuit.reset("groq")
            return (r.choices[0].message.content or ""), "groq"
        except Exception as e:
            print(f"[nimble] Groq stub failed: {type(e).__name__}: {str(e)[:160]}; trying Cerebras", flush=True)
            llm_circuit.classify_and_trip("groq", e)
            last_error = e
    elif _GROQ_KEY:
        print(f"[nimble] Groq circuit open ({llm_circuit.seconds_remaining('groq')}s); skipping", flush=True)

    if _CEREBRAS_KEY and not llm_circuit.is_open("cerebras"):
        try:
            c = AsyncOpenAI(api_key=_CEREBRAS_KEY, base_url="https://api.cerebras.ai/v1", timeout=_LLM_TIMEOUT_SEC, max_retries=0)
            r = await c.chat.completions.create(
                model=_CEREBRAS_MODEL, messages=messages, temperature=0.3, max_tokens=1024,
            )
            llm_circuit.reset("cerebras")
            return (r.choices[0].message.content or ""), "cerebras"
        except Exception as e:
            print(f"[nimble] Cerebras stub failed: {type(e).__name__}: {str(e)[:160]}", flush=True)
            llm_circuit.classify_and_trip("cerebras", e)
            last_error = e
    elif _CEREBRAS_KEY:
        print(f"[nimble] Cerebras circuit open ({llm_circuit.seconds_remaining('cerebras')}s); skipping", flush=True)

    raise last_error or RuntimeError("All LLM providers unavailable (all breakers open)")


async def _llm_stub(query: str) -> dict:
    """Generate route-specific search results via LLM when Nimble is unavailable.

    Short-circuits to the generic stub if the shared LLM breaker is open —
    no point hitting providers we already know are down.
    """
    if not _OPENROUTER_KEY and not _GROQ_KEY and not _CEREBRAS_KEY:
        return _generic_stub(query)
    if llm_circuit.is_open():
        # Every configured provider has its breaker open — go straight to
        # the generic stub instead of cycling through dead providers.
        print(f"[nimble] All LLM provider breakers open; using generic stub", flush=True)
        return _generic_stub(query)
    try:
        raw, _provider = await _call_llm_with_fallback(query)
        raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
        data = json.loads(raw)
        return {
            "query":   query,
            "summary": data.get("summary", ""),
            "sources": data.get("sources", []),
        }
    except Exception:
        return _generic_stub(query)


# ── Curated zone-specific sources ────────────────────────────────
#
# When both Nimble and the LLM stub are unavailable, this is the last
# resort. Instead of returning a generic homepage URL, we look at the
# query, identify the specific dead zone, and return real authoritative
# deep links for that zone (Port Authority for the Lincoln Tunnel,
# Caltrans for Big Sur, CDOT for Colorado passes, etc.).
#
# Each entry is keyed by a lowercase substring that uniquely identifies
# the zone in the query string. Each entry has weather/road/poi/news
# variants. If no zone matches, we fall through to the generic-but-
# better stubs at the bottom of _generic_stub.

_ZONE_SOURCES: dict[str, dict[str, dict]] = {
    # Lincoln Tunnel / Manhattan to Newark
    "lincoln tunnel": {
        "weather": {
            "summary": "Lincoln Tunnel weather (Manhattan to Weehawken). Currently clear with light westerly winds. No precipitation expected in the next 6 hours along the Hudson River crossing.",
            "sources": [
                {"url": "https://forecast.weather.gov/MapClick.php?lat=40.7614&lon=-74.0085", "title": "NWS — Manhattan / Hudson Crossing Forecast", "snippet": "Hourly forecast for the Hudson River crossing zone, updated every 60 minutes."},
                {"url": "https://www.weather.gov/okx/", "title": "NWS New York / Upton Office", "snippet": "Severe weather alerts and marine forecasts for the NYC metro area."},
                {"url": "https://www.wunderground.com/weather/us/nj/weehawken", "title": "Weehawken NJ Conditions", "snippet": "Live conditions at the NJ portal of the Lincoln Tunnel."},
            ],
        },
        "road": {
            "summary": "Lincoln Tunnel traffic (3 tubes, Manhattan ↔ Weehawken NJ). Center tube reversible by time of day. Tolls cashless via E-ZPass. Tube closures occasional 1–4 AM for maintenance.",
            "sources": [
                {"url": "https://www.panynj.gov/bridges-tunnels/en/lincoln-tunnel.html", "title": "Port Authority — Lincoln Tunnel", "snippet": "Official Port Authority page with live traffic conditions, toll rates, and tube-status updates."},
                {"url": "https://511nj.org/", "title": "511 NJ — Live Road Conditions", "snippet": "New Jersey statewide traffic, incidents and DOT alerts including Lincoln Tunnel approaches."},
                {"url": "https://www.panynj.gov/bridges-tunnels/en/traffic-advisory.html", "title": "Port Authority Traffic Advisories", "snippet": "Real-time alerts for Lincoln, Holland, GW Bridge, and Outerbridge crossings."},
            ],
        },
        "poi": {
            "summary": "Nearest services at the NJ portal: Vince Lombardi Service Area (NJ Turnpike MP 116E, ~5 min north) for fuel and food. Secaucus has Exxon, Wawa, and McDonalds within 1 mi of the tunnel exit.",
            "sources": [
                {"url": "https://www.njta.com/travel-resources/service-areas/vince-lombardi", "title": "Vince Lombardi Service Area (NJ Turnpike)", "snippet": "24/7 fuel, restrooms, ATM, Starbucks. ~3 mi from the Lincoln Tunnel NJ portal."},
                {"url": "https://www.exxon.com/en/find-station", "title": "Exxon Station Finder — Weehawken/Secaucus", "snippet": "Stations within 1 mile of the Lincoln Tunnel NJ side."},
                {"url": "https://www.panynj.gov/bus-terminals/en/port-authority.html", "title": "Port Authority Bus Terminal", "snippet": "Manhattan-side restrooms, food court and ground-transport options."},
            ],
        },
        "news": {
            "summary": "Local news for the Lincoln Tunnel / Hudson crossing area covers Port Authority operations, NJ-NY commuter issues, and Hudson County developments.",
            "sources": [
                {"url": "https://www.nj.com/hudson/", "title": "NJ.com — Hudson County News", "snippet": "Local news for Weehawken, Hoboken, Jersey City and the Lincoln Tunnel corridor."},
                {"url": "https://www.northjersey.com/news/", "title": "NorthJersey.com — News", "snippet": "Daily coverage of Port Authority decisions, NJ Transit, and crossing-related stories."},
                {"url": "https://www.nytimes.com/section/nyregion", "title": "NY Times — Metropolitan Region", "snippet": "NYC metro coverage including bridge and tunnel news."},
            ],
        },
    },

    # Newark McCarter Highway
    "newark": {
        "road": {
            "summary": "Newark McCarter Highway (NJ 21) connects the Lincoln Tunnel corridor to downtown Newark. Frequent construction near Newark Penn Station. Check NJDOT alerts before peak hours.",
            "sources": [
                {"url": "https://www.state.nj.us/transportation/commuter/roads/", "title": "NJDOT — Commuter Road Info", "snippet": "Live construction and incident updates for NJ state roads including NJ 21 / McCarter Hwy."},
                {"url": "https://511nj.org/", "title": "511 NJ", "snippet": "Statewide traffic conditions and incident reports."},
            ],
        },
        "news": {
            "summary": "Newark local news covers downtown construction, transit decisions, and Essex County developments.",
            "sources": [
                {"url": "https://www.nj.com/essex/", "title": "NJ.com — Essex County / Newark", "snippet": "Daily coverage of Newark, Essex County and Port Newark."},
                {"url": "https://www.tapinto.net/towns/newark", "title": "TAPinto Newark", "snippet": "Hyperlocal Newark news and events."},
            ],
        },
    },

    # Eisenhower Tunnel / I-70 Colorado
    "eisenhower": {
        "weather": {
            "summary": "Eisenhower-Johnson Memorial Tunnel sits at 11,158 ft on I-70 west of Denver. Expect rapid weather changes, afternoon thunderstorms in summer, and frequent winter chain laws.",
            "sources": [
                {"url": "https://forecast.weather.gov/MapClick.php?lat=39.6805&lon=-105.9111", "title": "NWS Eisenhower Tunnel Zone Forecast", "snippet": "11,000 ft elevation forecast for the I-70 corridor near Loveland Pass."},
                {"url": "https://avalanche.state.co.us/forecasts/backcountry-avalanche/vail-summit-county", "title": "CAIC — Vail & Summit County Avalanche", "snippet": "Daily avalanche forecast for the I-70 corridor."},
            ],
        },
        "road": {
            "summary": "Eisenhower Tunnel on I-70 — westbound (north bore) and eastbound (south bore). Chain laws activated 200+ days/year. Closures common during peak Front Range storms.",
            "sources": [
                {"url": "https://cotrip.org/", "title": "COTrip — Colorado I-70 Conditions", "snippet": "Live CDOT camera feeds for Eisenhower Tunnel and Loveland Pass approach."},
                {"url": "https://www.codot.gov/travel/eisenhower-tunnel", "title": "CDOT Eisenhower Tunnel Page", "snippet": "Official tunnel operations, chain law status, and closure history."},
            ],
        },
        "poi": {
            "summary": "Last fuel before Eisenhower Tunnel westbound: Silverthorne (15 mi east of tunnel). Dillon and Silverthorne have Conoco, Phillips 66, and 24/7 services. Frisco a few minutes further west.",
            "sources": [
                {"url": "https://www.gasbuddy.com/gasprices/colorado/silverthorne", "title": "GasBuddy — Silverthorne CO", "snippet": "Fuel stations within 10 mi of the I-70 / Eisenhower Tunnel approach."},
                {"url": "https://www.summitcountyco.gov/", "title": "Summit County, CO — Services", "snippet": "Emergency services, sheriff, and visitor info for Dillon/Silverthorne area."},
            ],
        },
        "news": {
            "summary": "Eisenhower Tunnel and I-70 mountain corridor news — closures, accidents, and CDOT operational updates.",
            "sources": [
                {"url": "https://summitdaily.com/", "title": "Summit Daily News", "snippet": "Local news for Dillon, Silverthorne, Breckenridge — covers I-70 incidents."},
                {"url": "https://denverpost.com/news/transportation/", "title": "Denver Post — Transportation", "snippet": "Mountain corridor coverage, CDOT news, and travel advisories."},
            ],
        },
    },

    # Vail Pass / I-70 Colorado
    "vail pass": {
        "weather": {
            "summary": "Vail Pass (10,662 ft, I-70 between Vail and Copper Mountain). Frequent storms and chain laws. Sub-zero temps common Oct–May.",
            "sources": [
                {"url": "https://forecast.weather.gov/MapClick.php?lat=39.5286&lon=-106.2189", "title": "NWS — Vail Pass Forecast", "snippet": "Zone forecast for Vail Pass and the upper I-70 corridor."},
                {"url": "https://avalanche.state.co.us/", "title": "Colorado Avalanche Information Center", "snippet": "Statewide avalanche forecasts including the Vail Pass zone."},
            ],
        },
        "road": {
            "summary": "Vail Pass on I-70 — chain laws and closures common. Adjacent recreational paths (Vail Pass bike trail) closed seasonally.",
            "sources": [
                {"url": "https://cotrip.org/", "title": "COTrip — I-70 Vail Pass Conditions", "snippet": "CDOT cameras and live status for Vail Pass."},
                {"url": "https://www.codot.gov/travel", "title": "CDOT Travel Center", "snippet": "Statewide closures, chain laws and mountain pass operations."},
            ],
        },
    },

    # Cajon Pass / I-15
    "cajon pass": {
        "weather": {
            "summary": "Cajon Pass on I-15 (4,190 ft) experiences strong cross-winds. Truck rollovers in high-wind events. Watch for sudden visibility drops from fog or dust.",
            "sources": [
                {"url": "https://forecast.weather.gov/MapClick.php?lat=34.3061&lon=-117.4742", "title": "NWS — Cajon Pass Forecast", "snippet": "Cajon Pass weather and wind advisories."},
            ],
        },
        "road": {
            "summary": "Cajon Pass is the primary I-15 connector between LA Basin and the High Desert. Heavy truck traffic. Caltrans incident alerts updated frequently.",
            "sources": [
                {"url": "https://quickmap.dot.ca.gov/", "title": "Caltrans QuickMap", "snippet": "Live traffic, camera feeds, and incident reports for I-15 / Cajon Pass."},
                {"url": "https://dot.ca.gov/programs/traffic-operations/road-information", "title": "Caltrans — Road Information", "snippet": "Statewide closures and construction including Cajon Pass."},
            ],
        },
    },

    # Mojave Desert / Baker
    "mojave": {
        "weather": {
            "summary": "Mojave Desert section of I-15 (Baker, Zzyzx, Halloran). Extreme summer heat — keep coolant levels topped. Limited services. Wind can spike to 50+ mph crossing the open valley.",
            "sources": [
                {"url": "https://forecast.weather.gov/MapClick.php?lat=35.2680&lon=-116.0697", "title": "NWS — Baker / Mojave Forecast", "snippet": "Desert zone forecast with heat advisories."},
            ],
        },
        "poi": {
            "summary": "Last reliable services before the Mojave dead zone: Baker, CA (Bun Boy, Mad Greek). Halloran Summit has limited fuel. Primm/Stateline NV next consistent service stop.",
            "sources": [
                {"url": "https://www.gasbuddy.com/gasprices/california/baker", "title": "GasBuddy — Baker, CA", "snippet": "Fuel prices and station hours for the Mojave I-15 corridor."},
                {"url": "https://www.bakerca.com/", "title": "Visit Baker CA", "snippet": "Town services and the famous World's Tallest Thermometer."},
            ],
        },
        "road": {
            "summary": "I-15 across the Mojave is a long, sparsely-trafficked stretch. CHP responses can be 20–30 min. Carry water, check fuel before Baker.",
            "sources": [
                {"url": "https://quickmap.dot.ca.gov/", "title": "Caltrans QuickMap — I-15", "snippet": "Live conditions across the Mojave desert section of I-15."},
            ],
        },
    },

    # Big Sur / Bixby Bridge / Highway 1 / Gorda
    "big sur": {
        "weather": {
            "summary": "Big Sur (Highway 1 between Carmel and San Simeon). Coastal fog common AM and evening. Winter storms can trigger landslides closing PCH for days/weeks.",
            "sources": [
                {"url": "https://forecast.weather.gov/MapClick.php?lat=36.2461&lon=-121.7714", "title": "NWS — Big Sur Coastal Forecast", "snippet": "Marine and coastal forecast for the Big Sur region."},
                {"url": "https://www.mtrnpark.org/visit/weather-conditions/", "title": "Big Sur Weather Conditions", "snippet": "Local Big Sur weather, surf, and wind reports."},
            ],
        },
        "road": {
            "summary": "Highway 1 through Big Sur — frequent landslide closures. Check Caltrans before driving. Bixby Bridge is the photo-stop landmark (mile marker 59.1).",
            "sources": [
                {"url": "https://quickmap.dot.ca.gov/", "title": "Caltrans QuickMap — Highway 1", "snippet": "Live road conditions for PCH including current closures."},
                {"url": "https://www.bigsurcalifornia.org/highway1.html", "title": "Big Sur Chamber — Highway 1 Status", "snippet": "Community-maintained status of Highway 1 closures and detours."},
            ],
        },
        "poi": {
            "summary": "Limited services on Highway 1 Big Sur: Big Sur Lodge, Nepenthe Restaurant, Big Sur Bakery, Gorda gas station (last fuel for ~60 mi). Cell coverage essentially zero between Carmel and San Simeon.",
            "sources": [
                {"url": "https://www.bigsurlodge.com/", "title": "Big Sur Lodge", "snippet": "Lodging, dining and fuel within Pfeiffer Big Sur State Park."},
                {"url": "https://gordaspringsresort.com/", "title": "Gorda Springs Resort", "snippet": "Last gas, food and lodging on Highway 1 between Big Sur and San Simeon."},
            ],
        },
    },

    "bixby bridge": {
        "road": {
            "summary": "Bixby Creek Bridge on Highway 1 (mile marker 59.1, Big Sur). Open-spandrel concrete arch built 1932. Single lane each direction. Stop only at pullouts.",
            "sources": [
                {"url": "https://quickmap.dot.ca.gov/", "title": "Caltrans QuickMap — Bixby Bridge", "snippet": "Live conditions and any restrictions for Bixby Bridge."},
            ],
        },
    },

    # US-50 Nevada / Bob Scott Summit / Austin Summit / Middlegate Station
    "us route 50 nevada": {
        "weather": {
            "summary": "US-50 in Nevada — the Loneliest Road in America. Sub-freezing temps in winter, extreme heat in summer. Carry water and extra fuel.",
            "sources": [
                {"url": "https://forecast.weather.gov/MapClick.php?lat=39.4583&lon=-117.3658", "title": "NWS — Central Nevada Forecast", "snippet": "Zone forecast for the US-50 central Nevada corridor."},
            ],
        },
        "road": {
            "summary": "US-50 across Nevada — sparse traffic, 70+ mph speed limits, snow drifts common winter. NDOT 511 for closures.",
            "sources": [
                {"url": "https://www.nvroads.com/", "title": "Nevada 511 — Road Conditions", "snippet": "Live NDOT camera feeds and incident reports including US-50."},
                {"url": "https://www.dot.nv.gov/", "title": "Nevada DOT", "snippet": "Statewide road operations and construction notices."},
            ],
        },
        "poi": {
            "summary": "Services on US-50 NV are 60–100 mi apart. Austin, NV is the largest stop between Ely and Fallon. Middlegate Station is the iconic shoe tree/cafe stop. Carry spare tire and water.",
            "sources": [
                {"url": "https://travelnevada.com/cities/austin/", "title": "Travel Nevada — Austin NV", "snippet": "Services, lodging and fuel in Austin, the midpoint of US-50."},
                {"url": "https://middlegatestation.net/", "title": "Middlegate Station", "snippet": "Iconic US-50 cafe, gas and the famous shoe tree."},
            ],
        },
        "news": {
            "summary": "Central Nevada and US-50 news — sparse but covers tourism, mining, and BLM/forest service operations along the corridor.",
            "sources": [
                {"url": "https://thisisreno.com/", "title": "This Is Reno", "snippet": "Northern Nevada news including US-50 corridor coverage."},
            ],
        },
    },

    # Million Dollar Highway / US-550 Colorado / Red Mountain Pass / Molas / Coal Bank
    "million dollar highway": {
        "weather": {
            "summary": "US-550 / Million Dollar Highway connects Ouray to Silverton to Durango — Red Mountain Pass (11,018 ft), Molas Pass (10,910 ft), Coal Bank Pass (10,640 ft). Snow possible any month above 10,000 ft.",
            "sources": [
                {"url": "https://forecast.weather.gov/MapClick.php?lat=37.8967&lon=-107.7128", "title": "NWS — Red Mountain Pass Forecast", "snippet": "Mountain forecast for the US-550 corridor."},
                {"url": "https://avalanche.state.co.us/", "title": "Colorado Avalanche Information Center", "snippet": "Daily avalanche forecast — Red Mountain Pass is one of CO's most avalanche-prone zones."},
            ],
        },
        "road": {
            "summary": "Million Dollar Highway has no guardrails on long stretches, hairpin switchbacks, and 1,000+ ft drop-offs. CDOT closes during major snowstorms.",
            "sources": [
                {"url": "https://cotrip.org/", "title": "COTrip — US-550 Conditions", "snippet": "Live CDOT data including Red Mountain Pass status."},
                {"url": "https://www.codot.gov/travel/scenic-byways/southwest/san-juan-skyway", "title": "CDOT — San Juan Skyway Byway", "snippet": "Official scenic byway guide including current conditions."},
            ],
        },
        "poi": {
            "summary": "Stops on US-550: Ouray (Hot Springs Pool, fuel), Silverton (small mining town, mid-point services), Durango (full services). Limited cell coverage between Ouray and Silverton.",
            "sources": [
                {"url": "https://www.ouraycolorado.com/", "title": "Visit Ouray, CO", "snippet": "Services, lodging and hot springs in Ouray — northern endpoint."},
                {"url": "https://silvertoncolorado.com/", "title": "Silverton, CO", "snippet": "Mid-route services in historic mining town."},
            ],
        },
    },

    # Transit
    "canarsie tunnel": {
        "road": {  # we use "road" for transit-alert topic mapping
            "summary": "L train Canarsie Tunnel (Bedford Av Brooklyn ↔ 1st Av Manhattan, under the East River). MTA service alerts post here. No cell service in tunnel.",
            "sources": [
                {"url": "https://new.mta.info/alerts/subway", "title": "MTA — Subway Alerts (L Train)", "snippet": "Live MTA service status, planned work, and alerts for the L line."},
                {"url": "https://new.mta.info/maps/subway", "title": "MTA Subway Map", "snippet": "Official map with the L train and connections."},
            ],
        },
        "news": {
            "summary": "Local commuter news for the L line corridor — Bedford to Union Square to Canarsie.",
            "sources": [
                {"url": "https://www.bkmag.com/", "title": "Brooklyn Magazine", "snippet": "Williamsburg / North Brooklyn news and culture."},
                {"url": "https://www.amny.com/", "title": "amNewYork — Transit", "snippet": "Daily NYC transit news including MTA decisions."},
            ],
        },
    },

    "transbay tube": {
        "road": {
            "summary": "BART Transbay Tube (Embarcadero SF ↔ West Oakland, under SF Bay). No cell service in tube. Live BART status for delays.",
            "sources": [
                {"url": "https://www.bart.gov/schedules/advisories", "title": "BART — Service Advisories", "snippet": "Live BART delays, maintenance, and service updates."},
                {"url": "https://www.511.org/transit", "title": "511.org Transit", "snippet": "Bay Area transit status across BART, Muni, AC Transit and Caltrain."},
            ],
        },
        "news": {
            "summary": "Bay Area transit news — BART operations, ridership, and Bay Bridge / Tube corridor issues.",
            "sources": [
                {"url": "https://www.sfchronicle.com/transportation/", "title": "SF Chronicle — Transportation", "snippet": "Bay Area transit coverage including BART."},
            ],
        },
    },
}


# Default deeper-link sources when no specific zone matches.
_DEFAULT_BY_TOPIC: dict[str, dict] = {
    "weather": {
        "summary": "Check the National Weather Service zone forecast for your specific area. Forecasts update every hour and include hourly precipitation, wind, and visibility.",
        "sources": [
            {"url": "https://forecast.weather.gov/", "title": "National Weather Service", "snippet": "Enter your route ZIP for a zone forecast and active alerts."},
            {"url": "https://www.wunderground.com/", "title": "Weather Underground", "snippet": "Crowdsourced station data with hyperlocal accuracy."},
        ],
    },
    "road": {
        "summary": "Check your state DOT's 511 service for live road conditions, incidents, and construction along your route before entering low-signal areas.",
        "sources": [
            {"url": "https://www.fhwa.dot.gov/trafficinfo/", "title": "FHWA — State 511 Travel Info Directory", "snippet": "Links to every state's 511 traffic information system."},
            {"url": "https://www.travelpacific.com/", "title": "Pacific Northwest Travel Info", "snippet": "Regional road condition aggregator."},
        ],
    },
    "poi": {
        "summary": "Plan fuel and rest stops before entering signal-dead zones. GasBuddy and iExit show the next service along most US highways.",
        "sources": [
            {"url": "https://www.gasbuddy.com/", "title": "GasBuddy — Find Cheap Gas", "snippet": "Live fuel prices and station hours."},
            {"url": "https://www.iexitapp.com/", "title": "iExit — Interstate Exit Guide", "snippet": "Services available at each interstate exit nationwide."},
        ],
    },
    "news": {
        "summary": "Local news outlets for the route region cover incidents, construction, and any travel advisories likely to affect your trip.",
        "sources": [
            {"url": "https://www.apnews.com/hub/transportation", "title": "AP News — Transportation", "snippet": "National coverage of transportation incidents and policy."},
        ],
    },
    "emergency": {
        "summary": "For mountain emergencies, dial 911 — works without cell service on many carriers. National Association for Search and Rescue lists county SAR teams by region.",
        "sources": [
            {"url": "https://www.nasar.org/find-a-team", "title": "NASAR — Find Your Local SAR Team", "snippet": "County-by-county SAR team directory."},
            {"url": "https://www.911.gov/", "title": "911.gov — Emergency Services", "snippet": "Official US emergency services portal."},
        ],
    },
}


def _classify_topic(q: str) -> str:
    """Map a query to one of: weather / road / poi / news / emergency."""
    if any(kw in q for kw in ["emergency", "search rescue", "sheriff", "911", " sar ", "rescue", "evac"]):
        return "emergency"
    if any(kw in q for kw in ["weather", "forecast", "storm", "wind", "rain", "snow", "fog", "temperature"]):
        return "weather"
    if any(kw in q for kw in ["road", "traffic", "construction", "closure", "service alert", "delay", "transit", "subway", "bart", "train", "dot", "highway", "tube", "tunnel"]):
        return "road"
    if any(kw in q for kw in ["gas", "fuel", "station", "rest stop", "food", "service", "exit", "lodge", "nearby"]):
        return "poi"
    if any(kw in q for kw in ["news", "incident", "update", "local"]):
        return "news"
    return "news"  # default — most useful generic catch


# Aliases — additional substrings that should resolve to the same zone
# even if the LLM didn't include the literal zone name in its search query.
# Maps "alias substring" -> "canonical zone key in _ZONE_SOURCES".
_ZONE_ALIASES: dict[str, str] = {
    "manhattan to newark":         "lincoln tunnel",
    "weehawken":                   "lincoln tunnel",
    "hudson river":                "lincoln tunnel",
    "mccarter hwy":                "newark",
    "mccarter highway":            "newark",
    "denver to vail":              "eisenhower",
    "i-70 colorado":               "eisenhower",
    "i-70":                        "eisenhower",
    "los angeles to las vegas":    "cajon pass",
    "la to las vegas":             "cajon pass",
    "i-15":                        "cajon pass",
    "baker":                       "mojave",
    "primm":                       "mojave",
    "stateline":                   "mojave",
    "carmel to san luis obispo":   "big sur",
    "highway 1":                   "big sur",
    "pch":                         "big sur",
    "gorda":                       "big sur",
    "ragged point":                "big sur",
    "ely to fallon":               "us route 50 nevada",
    "us-50":                       "us route 50 nevada",
    "loneliest road":              "us route 50 nevada",
    "bob scott summit":            "us route 50 nevada",
    "austin summit":               "us route 50 nevada",
    "middlegate":                  "us route 50 nevada",
    "ouray to durango":            "million dollar highway",
    "us-550":                      "million dollar highway",
    "red mountain pass":           "million dollar highway",
    "molas pass":                  "million dollar highway",
    "coal bank pass":              "million dollar highway",
    "silverton":                   "million dollar highway",
    "l train":                     "canarsie tunnel",
    "bedford av":                  "canarsie tunnel",
    "bart":                        "transbay tube",
    "embarcadero":                 "transbay tube",
    "west oakland":                "transbay tube",
}


def _resolve_zone(q: str) -> str | None:
    """Find a known zone key for this query.

    Prefers the LONGEST/most-specific match so "Manhattan to Newark"
    resolves to "lincoln tunnel" (via the alias) rather than to "newark"
    just because "newark" is a substring of the route name. The road
    section was already getting the right hit because the LLM included
    "Lincoln Tunnel" in road queries; this fixes the weather/poi/news
    sections that don't.
    """
    candidates: list[tuple[int, str]] = []
    for zone_key in _ZONE_SOURCES:
        if zone_key in q:
            candidates.append((len(zone_key), zone_key))
    for alias, canonical in _ZONE_ALIASES.items():
        if alias in q and canonical in _ZONE_SOURCES:
            candidates.append((len(alias), canonical))
    if not candidates:
        return None
    # Longest match wins.
    candidates.sort(reverse=True)
    return candidates[0][1]


def _generic_stub(query: str) -> dict:
    """Last-resort stub when both Nimble and the LLM are unavailable.

    Zone-aware: looks for a known dead zone (direct match or alias —
    route name, alternate landmark) in the query and returns curated
    real authoritative sources (Port Authority, NWS, CDOT, Caltrans,
    NDOT, MTA, BART). Falls back to deeper-linked generic sources when
    no specific zone matches.
    """
    q = query.lower()
    topic = _classify_topic(q)
    zone  = _resolve_zone(q)

    if zone and topic in _ZONE_SOURCES[zone]:
        entry = _ZONE_SOURCES[zone][topic]
        return {"query": query, "summary": entry["summary"], "sources": list(entry["sources"])}

    # Fallback path B: if zone matched but THIS topic wasn't curated for
    # that zone, still mention the zone in the default summary so the
    # user sees specificity.
    default = _DEFAULT_BY_TOPIC.get(topic, _DEFAULT_BY_TOPIC["news"])
    summary = default["summary"]
    if zone:
        summary = f"For the {zone} area: {summary}"
    return {"query": query, "summary": summary, "sources": list(default["sources"])}


@tool(name="nimble_search")
async def search(query: str) -> dict:
    """Web search via Nimble. Returns {query, summary, sources}.
    Falls back to LLM-generated route-specific content when Nimble is unavailable."""
    await emit({"type": "tool", "name": "nimble", "query": query})
    if not _API_KEY:
        result = await _llm_stub(query)
        result["sources"] = await _validate_sources(result.get("sources", []))
        try:
            LLMObs.annotate(
                input_data=query,
                output_data=result["summary"],
                metadata={"backend": "llm_stub", "source_count": len(result["sources"])},
                tags={"tool": "nimble_search"},
            )
        except Exception:
            pass
        return result
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                NIMBLE_URL,
                headers={"Authorization": f"Basic {_API_KEY}"},
                json={"query": query, "country": "US", "locale": "en", "render": False},
            )
            resp.raise_for_status()
            data = resp.json()
        # Best-effort extraction — exact shape varies, so on any parse issue we fall back.
        organic = (data.get("parsing", {}).get("entities", {}).get("OrganicResult")
                   or data.get("organic_results")
                   or [])
        sources = []
        for item in organic[:8]:   # extra candidates — reachable ones are picked first after URL check
            sources.append({
                "url": item.get("url") or item.get("link") or "",
                "title": item.get("title") or item.get("displayed_title") or "",
                "snippet": item.get("snippet") or item.get("description") or "",
            })
        if not sources:
            result = await _llm_stub(query)
        else:
            summary = " ".join(s["snippet"] for s in sources[:2]) or (await _llm_stub(query))["summary"]
            result = {"query": query, "summary": summary, "sources": sources}
        result["sources"] = await _validate_sources(result.get("sources", []))
        try:
            LLMObs.annotate(
                input_data=query,
                output_data=result["summary"],
                metadata={"backend": "nimble", "source_count": len(result["sources"])},
                tags={"tool": "nimble_search"},
            )
        except Exception:
            pass
        return result
    except Exception as e:
        await emit({"type": "log", "level": "warn",
                    "msg": f"nimble failed ({e!s}); using llm_stub"})
        result = await _llm_stub(query)
        result["sources"] = await _validate_sources(result.get("sources", []))
        try:
            LLMObs.annotate(
                input_data=query,
                output_data=result["summary"],
                metadata={"backend": "llm_stub_after_error", "error": str(e)},
                tags={"tool": "nimble_search"},
            )
        except Exception:
            pass
        return result
