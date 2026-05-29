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
            "summary": (
                "LINCOLN TUNNEL WEATHER (Manhattan → Weehawken NJ).\n"
                "Tunnel is fully enclosed — no precipitation impact inside. "
                "Watch for: low visibility at NJ portal (frequent fog Oct–Mar), "
                "strong cross-winds on the helix approach (sustained 25+ mph closes high-profile vehicles).\n"
                "Typical conditions this time of year: 45–65°F, NW winds 8–15 mph.\n"
                "Emergency closure alerts: tune AM 1630 (Port Authority radio) inside tunnel."
            ),
            "sources": [
                {"url": "https://forecast.weather.gov/MapClick.php?lat=40.7614&lon=-74.0085", "title": "NWS — Manhattan Forecast (online)", "snippet": "Reference when back online: hourly forecast updated every 60 min."},
                {"url": "https://www.weather.gov/okx/", "title": "NWS NY/Upton Office (online)", "snippet": "Severe weather alerts for the NYC metro area."},
            ],
        },
        "road": {
            "summary": (
                "LINCOLN TUNNEL TRAFFIC — 3 tubes, ~1.5 mi each, Manhattan ↔ Weehawken NJ.\n"
                "• Tolls: $16.00 peak / $13.75 off-peak (E-ZPass) — cashless, no toll booths\n"
                "• Center tube REVERSIBLE: NB mornings, SB evenings (XBL bus lane mornings)\n"
                "• Tube closures common 1–4 AM weeknights for maintenance\n"
                "• Inside-tunnel emergencies: pull to right shoulder, use white emergency phones every 300 ft\n"
                "• Port Authority Police: (855) 447-2255 (works from emergency phones)\n"
                "• Tunnel radio: AM 1630 for live status (works inside tunnel)\n"
                "• NJ approach: NJ-495 → tunnel helix (3 right-curving levels)\n"
                "• Manhattan exit: 40th St / 39th St (3 lanes each direction)"
            ),
            "sources": [
                {"url": "https://www.panynj.gov/bridges-tunnels/en/lincoln-tunnel.html", "title": "Port Authority — Lincoln Tunnel (online)", "snippet": "Reference when back online: live traffic and toll updates."},
                {"url": "https://511nj.org/", "title": "511 NJ — Live Road Conditions (online)", "snippet": "Statewide NJ traffic and DOT alerts."},
            ],
        },
        "poi": {
            "summary": (
                "SERVICES NEAR THE LINCOLN TUNNEL\n\n"
                "NJ side (Weehawken / Secaucus):\n"
                "• Vince Lombardi Service Area — NJ Turnpike MP 116E, 24/7. Sunoco fuel, Starbucks, Burger King, restrooms, ATM. ~3 mi north of tunnel via NJ-495 → NJTP\n"
                "• Exxon Weehawken — 700 Park Ave, 24/7. ~0.4 mi from NJ portal\n"
                "• Wawa Secaucus — 1300 Paterson Plank Rd, 24/7. Fuel + food, ~1 mi from tunnel\n"
                "• Hoboken/JC fuel: limited, mostly closed overnight\n\n"
                "Manhattan side:\n"
                "• Port Authority Bus Terminal — 8th Ave & 42nd St. Restrooms, food court (Au Bon Pain, Pret, McDonald's). Open ~5 AM – 1 AM\n"
                "• Times Square subway: 42nd St (1/2/3, N/Q/R/W, 7, S) — 1 block from tunnel exit"
            ),
            "sources": [
                {"url": "https://www.njta.com/travel-resources/service-areas/vince-lombardi", "title": "Vince Lombardi Service Area page (online)", "snippet": "Hours, amenities, exact NJTP milepost."},
            ],
        },
        "news": {
            "summary": (
                "LINCOLN TUNNEL / HUDSON CROSSING CONTEXT\n\n"
                "Coverage area: Weehawken, Hoboken, Jersey City, Hudson County NJ + West Side Manhattan.\n"
                "Common recurring issues to expect:\n"
                "• AM peak (7–10 AM): NJ→NYC backups extend to NJ-495 and NJ-3 merge — 15–30 min delay typical\n"
                "• PM peak (4–7 PM): NYC→NJ backups extend through Manhattan to 9th Ave\n"
                "• Friday afternoons: heaviest week — XBL (bus lane) helps westbound\n"
                "• Major events at MetLife Stadium add 20–40 min to NJ-bound trips\n"
                "When back online: NJ.com Hudson County, NorthJersey.com, ABC7 Eyewitness News for live updates."
            ),
            "sources": [
                {"url": "https://www.nj.com/hudson/", "title": "NJ.com Hudson County (online)", "snippet": "Local Weehawken/Hoboken/JC news."},
                {"url": "https://www.northjersey.com/news/", "title": "NorthJersey.com (online)", "snippet": "Daily Port Authority coverage."},
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
            "summary": (
                "EISENHOWER TUNNEL WEATHER — 11,158 ft elevation on I-70 west of Denver.\n"
                "• Tunnel interior fully enclosed and climate-controlled — no weather impact inside\n"
                "• APPROACH zones above 11,000 ft: weather changes minute-to-minute\n"
                "• Summer (Jun–Aug): afternoon thunderstorms most days 1–5 PM, hail possible\n"
                "• Winter (Oct–May): chain laws activate ~200 days/yr; closures during heavy snow\n"
                "• Tunnel itself stays open in nearly all conditions; bottleneck is the APPROACH\n"
                "• Carry blankets and water Oct–April — closure can strand you 2–8 hours\n"
                "• Tune AM 1610 inside tunnel for live closure updates"
            ),
            "sources": [
                {"url": "https://forecast.weather.gov/MapClick.php?lat=39.6805&lon=-105.9111", "title": "NWS Loveland Pass Forecast (online)", "snippet": "Reference: 11,000 ft elevation zone forecast."},
                {"url": "https://avalanche.state.co.us/forecasts/backcountry-avalanche/vail-summit-county", "title": "CAIC Vail/Summit Avalanche (online)", "snippet": "Daily backcountry avalanche advisory."},
            ],
        },
        "road": {
            "summary": (
                "EISENHOWER-JOHNSON MEMORIAL TUNNEL on I-70.\n"
                "• Westbound: north bore (Eisenhower). Eastbound: south bore (Johnson). Two lanes each direction.\n"
                "• Length: 1.7 mi. Speed limit 50 mph (heavily enforced).\n"
                "• Vehicle restrictions: NO oversized loads (>13'6\" height, >13'6\" width). HAZMAT permitted with restrictions.\n"
                "• Chain laws activate ~200 days/year. Code 18 = passenger chains required. Code 16 = traction only.\n"
                "• Inside tunnel: pull to right shoulder for emergencies. Emergency phones every 300 ft.\n"
                "• Tunnel control: (303) 569-2118 (CDOT)\n"
                "• Inside-tunnel radio: AM 1610 — auto-tunes for closure/chain announcements\n"
                "• Common closure trigger: I-70 corridor accidents, not the tunnel itself"
            ),
            "sources": [
                {"url": "https://www.codot.gov/travel/eisenhower-tunnel", "title": "CDOT Eisenhower Tunnel Page (online)", "snippet": "Reference: live tunnel status when reconnected."},
                {"url": "https://cotrip.org/", "title": "COTrip Live I-70 Cameras (online)", "snippet": "CDOT cameras for Eisenhower and Loveland Pass approaches."},
            ],
        },
        "poi": {
            "summary": (
                "SERVICES ON I-70 NEAR EISENHOWER TUNNEL\n\n"
                "Westbound (Denver → Vail), LAST FUEL BEFORE TUNNEL:\n"
                "• Silverthorne (exit 205, 15 mi east of tunnel) — Conoco, Shell, Phillips 66 all 24/7\n"
                "• Dillon (exit 205) — Conoco at 800 Anemone Trail, City Market grocery, McDonald's\n\n"
                "Westbound AFTER tunnel:\n"
                "• Frisco (exit 201) — Conoco, 7-Eleven, multiple restaurants\n"
                "• Copper Mountain (exit 195) — limited (resort only)\n"
                "• Vail Pass summit (exit 190) — rest area, no fuel\n"
                "• Vail (exit 173) — full services\n\n"
                "Emergency contacts:\n"
                "• Summit County Sheriff: (970) 453-2232\n"
                "• Frisco/Copper SAR (Search & Rescue): dial 911 — Summit County SAR dispatched\n"
                "• Vail Mountain Rescue: (970) 569-2191"
            ),
            "sources": [
                {"url": "https://www.summitcountyco.gov/", "title": "Summit County, CO Services (online)", "snippet": "Reference: county services and emergency contacts."},
            ],
        },
        "news": {
            "summary": (
                "I-70 MOUNTAIN CORRIDOR — EXPECTED CONDITIONS\n\n"
                "• Sunday returns (3–8 PM): heaviest week — \"the Sunday slog\". EB I-70 can crawl from Vail Pass to Denver\n"
                "• Friday departures (3–9 PM): heavy WB Denver → ski country\n"
                "• Eisenhower closures usually run 30 min – 3 hours; weather-induced can be longer\n"
                "• When tunnel closes, US-6 over Loveland Pass becomes the alternate (10,990 ft, switchbacks, no commercial vehicles)\n\n"
                "When back online: Summit Daily News (Frisco/Dillon area), Denver Post Transportation."
            ),
            "sources": [
                {"url": "https://summitdaily.com/", "title": "Summit Daily News (online)", "snippet": "Local news Frisco/Dillon/Breckenridge."},
                {"url": "https://denverpost.com/news/transportation/", "title": "Denver Post Transportation (online)", "snippet": "Daily I-70 corridor coverage."},
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
            "summary": (
                "CAJON PASS WEATHER — I-15 between San Bernardino and Victorville (4,190 ft summit).\n"
                "• Strong sustained CROSS-WINDS year-round, peaking 40–60 mph fall/winter\n"
                "• HIGH-PROFILE VEHICLE warnings issued via I-15 message boards when winds exceed 35 mph sustained\n"
                "• Dust storm potential: visibility can drop to <100 ft in seconds\n"
                "• Fog: thick at the SUMMIT in early morning Nov–Feb\n"
                "• Summer: ambient 95–110°F at the desert end (Victorville). Carry water.\n"
                "• If a truck rollover is reported ahead, stay in vehicle until CHP clears scene\n"
                "• Tune AM 1700 for desert highway advisories (intermittent)"
            ),
            "sources": [
                {"url": "https://forecast.weather.gov/MapClick.php?lat=34.3061&lon=-117.4742", "title": "NWS Cajon Pass Forecast (online)", "snippet": "Reference: hourly wind + visibility forecast."},
            ],
        },
        "road": {
            "summary": (
                "CAJON PASS — I-15, primary LA Basin ↔ High Desert / Vegas corridor.\n"
                "• Climb from ~1,200 ft (San Bernardino) to 4,190 ft summit in ~20 mi\n"
                "• 5 lanes each direction at the bottom, narrows to 4 at summit\n"
                "• HEAVY truck traffic 24/7 — stay out of the right lane on the climb\n"
                "• Key exits (SB → NB): 138 (Glen Helen), 131 (Cajon Blvd/Old 66), 129 (Hwy 138), 123 (Hesperia/Main St)\n"
                "• Cleghorn Pass alternate (Hwy 138 → Hwy 18) when I-15 closes — adds ~30 min\n"
                "• Emergency contacts:\n"
                "  - CHP Inland Division: (909) 383-4247\n"
                "  - San Bernardino Co Sheriff (Victorville): (760) 552-6800\n"
                "  - CHP enhanced emergency dial: *11 from any cell"
            ),
            "sources": [
                {"url": "https://quickmap.dot.ca.gov/", "title": "Caltrans QuickMap I-15 (online)", "snippet": "Reference: live cameras + incidents."},
            ],
        },
        "poi": {
            "summary": (
                "SERVICES ON CAJON PASS (I-15)\n\n"
                "Southbound (Vegas → LA) — last fuel before LA Basin:\n"
                "• Hesperia (exit 153A, Main St) — Shell, Chevron, Arco. Multiple 24/7 stations.\n"
                "• Victorville (exit 147–150) — full services, In-N-Out, fast food\n"
                "• Oak Hills (exit 138/139) — limited\n"
                "• Glen Helen (exit 138) — last stop before SB City\n\n"
                "Northbound (LA → Vegas) — last fuel before Mojave desert:\n"
                "• Victorville (exit 147) — full services, last cheap fuel\n"
                "• Hesperia / Main St — fuel + food\n"
                "• Barstow (exit 184, ~45 mi north of summit) — last full services before deep Mojave\n\n"
                "Rest areas: NONE on I-15 between Devore and Victorville (use exits)"
            ),
            "sources": [],
        },
    },

    # Mojave Desert / Baker
    "mojave": {
        "weather": {
            "summary": (
                "MOJAVE DESERT WEATHER — I-15 between Barstow and Primm NV.\n"
                "• Summer (Jun–Sep): 100–120°F daytime. Heat advisories near-daily.\n"
                "• Winter (Dec–Feb): can drop below 30°F overnight at higher elevation (Halloran Summit, 4,400 ft)\n"
                "• High wind warnings: 50+ mph sustained, dust storms reduce visibility to zero\n"
                "• If stranded in summer: stay WITH the vehicle (not under it — heat reflects up), wait for CHP\n"
                "• Carry 1 gallon water per person per day MINIMUM. Sun protection critical.\n"
                "• Cell coverage essentially zero between Yermo and Primm"
            ),
            "sources": [
                {"url": "https://forecast.weather.gov/MapClick.php?lat=35.2680&lon=-116.0697", "title": "NWS Baker / Mojave Forecast (online)", "snippet": "Reference: desert zone heat advisories."},
            ],
        },
        "poi": {
            "summary": (
                "MOJAVE I-15 SERVICES — LAST CHANCE STOPS\n\n"
                "Heading north (LA → Vegas):\n"
                "• Barstow (exit 184) — last full services for 50+ mi. Full fuel, Del Taco, Carl's Jr, In-N-Out.\n"
                "• Yermo (exit 191) — Eddie World (big convenience store), fuel\n"
                "• Calico Ghost Town (exit 191) — tourist stop, limited\n"
                "• Baker (exit 246) — FAMOUS midway stop:\n"
                "  - Bun Boy / Bun Boy Motel — diner since 1926\n"
                "  - Mad Greek Cafe — gyros, open 24/7\n"
                "  - World's Tallest Thermometer (134 ft) landmark\n"
                "  - Shell + Arco fuel\n"
                "• Halloran Summit (no exit number, 4,400 ft) — single closed truck stop, no services\n"
                "• Primm NV (exit 1, state line) — full services, Whiskey Pete's casino, fuel + food\n\n"
                "Emergency:\n"
                "• Mojave National Preserve dispatch: (760) 252-6100\n"
                "• San Bernardino Co Sheriff (Baker substation): (760) 733-4448\n"
                "• If broken down: stay with vehicle, run AC sparingly, conserve fuel"
            ),
            "sources": [],
        },
        "road": {
            "summary": (
                "I-15 ACROSS THE MOJAVE — Barstow to Primm NV (~145 mi)\n"
                "• Speed limit: 70 mph most of route\n"
                "• 2 lanes each direction, generally lightly trafficked except weekends\n"
                "• CHP response can take 20–45 minutes due to distance\n"
                "• Vegas-bound Friday afternoon (3–8 PM) backups at Primm + state-line\n"
                "• LA-bound Sunday afternoon (12–6 PM) backups at Primm + Baker\n"
                "• Closures: dust storm and crash both cause multi-hour shutdowns\n"
                "• Detour: NONE practical — Hwy 95 + Hwy 58 adds 4+ hours"
            ),
            "sources": [],
        },
    },

    # Big Sur / Bixby Bridge / Highway 1 / Gorda
    "big sur": {
        "weather": {
            "summary": (
                "BIG SUR WEATHER — Highway 1 (Carmel → San Simeon, ~90 mi)\n"
                "• Coastal fog: forms most mornings May–Sep, burns off ~10 AM–noon\n"
                "• Winter storms: landslides above mile marker 36 (Mud Creek) close PCH for weeks at a time\n"
                "• Year-round: bring layers — temps drop 15–20°F entering fog\n"
                "• High wind advisory thresholds: 35+ mph sustained closes Bixby Bridge to high-profile vehicles\n"
                "• Tsunami warning zone — if you feel a strong earthquake, drive INLAND immediately"
            ),
            "sources": [
                {"url": "https://forecast.weather.gov/MapClick.php?lat=36.2461&lon=-121.7714", "title": "NWS Big Sur Coastal Forecast (online)", "snippet": "Reference: marine and coastal hourly forecast."},
            ],
        },
        "road": {
            "summary": (
                "HIGHWAY 1 (PCH) THROUGH BIG SUR\n"
                "• Single lane each direction, 25–55 mph zones, no passing in most sections\n"
                "• Landmarks (north to south):\n"
                "  - Bixby Creek Bridge — MM 59.1 (photo stop, pullouts only)\n"
                "  - Pfeiffer Big Sur State Park — MM 47\n"
                "  - McWay Falls (Julia Pfeiffer Burns SP) — MM 35.8\n"
                "  - Lucia — MM 25 (lodging)\n"
                "  - Gorda — MM 13 (LAST FUEL going south for ~60 mi)\n"
                "  - Ragged Point — MM 2 (lodging + fuel)\n"
                "  - San Simeon (Hearst Castle) — MM -0\n"
                "• Closures: ALWAYS verify before committing past Carmel — landslide closures can require 100+ mi detour via US-101\n"
                "• Emergency: Monterey Co Sheriff (831) 755-3700; CHP Monterey (831) 770-8112\n"
                "• Cell coverage essentially ZERO between Carmel and San Simeon"
            ),
            "sources": [
                {"url": "https://www.bigsurcalifornia.org/highway1.html", "title": "Big Sur Chamber Hwy 1 Status (online)", "snippet": "Community-maintained closure status."},
                {"url": "https://quickmap.dot.ca.gov/", "title": "Caltrans QuickMap (online)", "snippet": "Live state-route conditions when back online."},
            ],
        },
        "poi": {
            "summary": (
                "BIG SUR SERVICES — Hwy 1, north to south\n\n"
                "• Carmel Highlands: full services (last full grocery before Big Sur)\n"
                "• Rocky Point Restaurant — MM 60, ocean views, lunch + dinner\n"
                "• Big Sur Lodge — MM 47, in Pfeiffer Big Sur SP. Rooms + restaurant + small store. (831) 667-3100\n"
                "• Big Sur Bakery — MM 45, breakfast + lunch + bakery\n"
                "• Nepenthe — MM 44, iconic clifftop restaurant\n"
                "• Deetjen's Big Sur Inn — MM 44, rustic lodging\n"
                "• Post Ranch Inn / Ventana — MM 44, luxury\n"
                "• Lucia Lodge — MM 25, ocean cabins + restaurant\n"
                "• Gorda Springs Resort — MM 13, LAST FUEL going south, small store + cafe + rooms\n"
                "• Ragged Point Inn — MM 2, fuel + restaurant + rooms\n\n"
                "EMERGENCIES (no cell):\n"
                "• Use CHP emergency call boxes — yellow, every ~5 mi on Hwy 1\n"
                "• Monterey Co Sheriff: (831) 755-3700\n"
                "• Big Sur Volunteer Fire: (831) 667-2113\n"
                "• Coast Guard (Monterey): (831) 647-7300"
            ),
            "sources": [
                {"url": "https://www.bigsurlodge.com/", "title": "Big Sur Lodge (online)", "snippet": "Reservations and current status."},
                {"url": "https://gordaspringsresort.com/", "title": "Gorda Springs Resort (online)", "snippet": "Last fuel for ~60 mi heading south."},
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
            "summary": (
                "US-50 NEVADA — THE LONELIEST ROAD IN AMERICA (Ely → Fallon, ~260 mi)\n"
                "• Summer (Jun–Aug): 90–105°F daytime in valleys, 75–85°F at passes\n"
                "• Winter (Nov–Mar): sub-zero overnight at passes, ice + snow drifts common\n"
                "• Wind: strong in afternoons, dust devils across playas\n"
                "• Visibility hazard: smoke from western wildfires Jul–Oct\n"
                "• Lightning: thunderstorms Jun–Aug afternoons, mountain summits dangerous\n"
                "• If stranded: stay with vehicle. CHP/NHP can take 1–2 hrs to respond.\n"
                "• Carry: 5+ gallons of water, blankets, full tank of fuel before each leg"
            ),
            "sources": [
                {"url": "https://forecast.weather.gov/MapClick.php?lat=39.4583&lon=-117.3658", "title": "NWS Central Nevada Forecast (online)", "snippet": "Reference: Austin/Eureka zone forecast."},
            ],
        },
        "road": {
            "summary": (
                "US-50 NEVADA — STAYING ALIVE ON THE LONELIEST ROAD\n"
                "• Speed limit: 70 mph open desert, 25–45 mph through small towns\n"
                "• Cell coverage: essentially ZERO between Ely and Fallon (Verizon spotty at Austin only)\n"
                "• Three major passes east to west:\n"
                "  - Bob Scott Summit (7,195 ft, MM 51 from Austin)\n"
                "  - Austin Summit (7,484 ft, MM 41 from Austin)\n"
                "  - Middlegate / Eastgate area (no high pass)\n"
                "• Snow chains: Dec–Mar over passes\n"
                "• Wildlife: deer/elk most active dawn/dusk, antelope herds cross unexpectedly\n"
                "• Emergency:\n"
                "  - Nevada Highway Patrol: *NHP (*647) from cell, (775) 689-4600 office\n"
                "  - Lander County Sheriff (Austin): (775) 964-2380\n"
                "  - Churchill County Sheriff (Fallon): (775) 423-3116\n"
                "  - REAL ID-style help: download the Nevada 511 app BEFORE leaving"
            ),
            "sources": [
                {"url": "https://www.nvroads.com/", "title": "Nevada 511 (online)", "snippet": "Reference: live NDOT cameras + incidents."},
            ],
        },
        "poi": {
            "summary": (
                "US-50 SERVICES — ELY TO FALLON\n\n"
                "From east to west (most reliable stops):\n"
                "• Ely, NV — full services, eastern endpoint. Last full fuel station east.\n"
                "• Eureka, NV (~80 mi west of Ely) — Owl Club Casino, fuel, motel, cafe\n"
                "• Austin, NV (~70 mi west of Eureka) — MIDPOINT. International Cafe, Cozy Mountain Motel, Chevron fuel. (775) 964-2200\n"
                "• Bob Scott Summit — small picnic area, no services\n"
                "• Cold Springs Station (~50 mi west of Austin) — fuel + cafe + bar (limited hours)\n"
                "• Middlegate Station — ICONIC. Cafe + bar + gas + the famous SHOE TREE landmark. (775) 423-7134\n"
                "• Fallon, NV — western endpoint, full services, Walmart\n\n"
                "RULE: Top off fuel at EVERY stop. The next one is 60+ miles away.\n\n"
                "Emergency / lodging:\n"
                "• Pony Express RV Park (Austin): (775) 964-2014\n"
                "• Highland Trail Lodge (Eureka): (775) 237-5331"
            ),
            "sources": [
                {"url": "https://middlegatestation.net/", "title": "Middlegate Station (online)", "snippet": "Iconic US-50 cafe + the shoe tree."},
            ],
        },
        "news": {
            "summary": (
                "US-50 / CENTRAL NEVADA CONTEXT\n\n"
                "• Highway 50 named the Loneliest Road by Life Magazine in 1986\n"
                "• Most closures: winter snow on passes (Bob Scott + Austin), spring flash floods\n"
                "• Tourism boom Jun–Sep — passport-stamp drivers + national-park visitors\n"
                "• Mining country: watch for slow-moving heavy equipment\n"
                "• Wildfire season Jul–Oct closes lateral roads (95/93), forcing US-50 detours\n\n"
                "When back online: This Is Reno, Eureka Sentinel, Reese River Reveille (Austin) for local updates."
            ),
            "sources": [
                {"url": "https://thisisreno.com/", "title": "This Is Reno (online)", "snippet": "Northern NV news including US-50 corridor."},
            ],
        },
    },

    # Million Dollar Highway / US-550 Colorado / Red Mountain Pass / Molas / Coal Bank
    "million dollar highway": {
        "weather": {
            "summary": (
                "MILLION DOLLAR HIGHWAY (US-550) WEATHER — Ouray → Silverton → Durango\n"
                "• Three passes above 10,000 ft. Snow POSSIBLE ANY MONTH.\n"
                "  - Red Mountain Pass: 11,018 ft\n"
                "  - Molas Pass: 10,910 ft\n"
                "  - Coal Bank Pass: 10,640 ft\n"
                "• Most avalanche-prone highway in Colorado. Avoid after fresh snow Nov–May.\n"
                "• Summer: thunderstorms afternoon, lightning above treeline\n"
                "• Winter: chain laws + frequent closures\n"
                "• Pre-storm rule: if CDOT mentions closure on US-550 forecast, turn around\n"
                "• Carry tow strap, sand/kitty litter, emergency blankets year-round"
            ),
            "sources": [
                {"url": "https://forecast.weather.gov/MapClick.php?lat=37.8967&lon=-107.7128", "title": "NWS Red Mountain Pass Forecast (online)", "snippet": "Reference: 11,000 ft elevation forecast."},
                {"url": "https://avalanche.state.co.us/", "title": "CAIC (online)", "snippet": "Reference: daily backcountry avalanche advisory."},
            ],
        },
        "road": {
            "summary": (
                "US-550 MILLION DOLLAR HIGHWAY — NO GUARDRAILS, NO MARGIN FOR ERROR\n"
                "• 25 miles of switchbacks Ouray → Silverton\n"
                "• Hairpin turns 15 mph posted, narrow lanes, NO guardrails on long stretches\n"
                "• 1,000+ ft drop-offs on the outside lane (southbound = outside)\n"
                "• Speed limit: 25–50 mph, drops to 15 mph on switchbacks\n"
                "• Avalanche shed at Riverside Slide protects Red Mtn Pass — but pass closes anyway during big slide events\n"
                "• Cell coverage: essentially ZERO between Ouray and Silverton\n"
                "• In an accident: do NOT stand on the road shoulder — there often isn't one. Move uphill side.\n"
                "• Emergency contacts:\n"
                "  - San Miguel Co Sheriff (Ouray): (970) 626-5670\n"
                "  - San Juan Co Sheriff (Silverton): (970) 387-5531\n"
                "  - La Plata Co Sheriff (Durango): (970) 247-1157\n"
                "  - Ouray Mountain Rescue: (970) 325-7000\n"
                "  - San Juan SAR (Silverton): dial 911"
            ),
            "sources": [
                {"url": "https://cotrip.org/", "title": "COTrip US-550 (online)", "snippet": "Reference: CDOT live conditions."},
            ],
        },
        "poi": {
            "summary": (
                "MILLION DOLLAR HIGHWAY SERVICES (north to south)\n\n"
                "OURAY (northern endpoint):\n"
                "• Switzerland of America Motel: (970) 325-4577\n"
                "• Wiesbaden Hot Springs Spa: natural hot springs, (970) 325-4347\n"
                "• Maggie's Kitchen — diner, breakfast/lunch\n"
                "• True Grit Cafe — full menu\n"
                "• Last gas before Red Mountain Pass: Ouray Conoco (425 Main St)\n\n"
                "ON THE WAY:\n"
                "• Idarado Mine ruins (mile MP 88) — photo stop only\n"
                "• Red Mountain Pass summit (MP 80) — no services\n"
                "• Molas Pass overlook (MP 64) — Andrews Lake parking\n\n"
                "SILVERTON (mid-point, 9,318 ft):\n"
                "• Silverton Standard / Wyman Hotel\n"
                "• Avon Hotel: (970) 387-5454\n"
                "• Brown Bear Cafe — lunch + dinner\n"
                "• Pickle Barrel — bar/grill\n"
                "• Fuel: Conoco at 1228 Greene St (limited winter hours)\n\n"
                "DURANGO (southern endpoint): full services\n\n"
                "Hospital: Mercy Hospital Durango — (970) 247-4311"
            ),
            "sources": [
                {"url": "https://www.ouraycolorado.com/", "title": "Visit Ouray (online)", "snippet": "Reference: Ouray services + lodging."},
                {"url": "https://silvertoncolorado.com/", "title": "Silverton CO (online)", "snippet": "Reference: mid-route services."},
            ],
        },
    },

    # Transit
    "canarsie tunnel": {
        "road": {  # transit-alert topic
            "summary": (
                "L TRAIN — CANARSIE TUNNEL (Bedford Av Brooklyn ↔ 1st Av Manhattan)\n"
                "• 1.4 mi under the East River, opened 1924\n"
                "• Run time Bedford ↔ 1st Av: ~5 min normally, no intermediate stops\n"
                "• Headways: 4 min peak, 6–10 min off-peak, 20 min late-night\n"
                "• ZERO cell service in tunnel — your phone reconnects at 1st Av or Bedford\n"
                "• Service interruptions usually announced via train PA\n"
                "• L train at Union Sq connects: 4/5/6, N/Q/R/W, F/M, PATH (14th St 6 Av)\n"
                "• L train at 1st Av: standalone — closest connection is M14 SBS at 14th St + 1st Av\n"
                "• L train at Bedford Av: walk 5 min to J/M/Z at Marcy Av\n\n"
                "IF STUCK IN TUNNEL:\n"
                "• Stay on train. Do NOT exit unless directed by MTA personnel.\n"
                "• MTA Emergency: 511 (when reconnected), or use train intercom\n"
                "• Subway emergency hotline: (888) 692-7233 (works above ground)"
            ),
            "sources": [
                {"url": "https://new.mta.info/alerts/subway", "title": "MTA Subway Alerts L Train (online)", "snippet": "Reference: live alerts when reconnected."},
            ],
        },
        "news": {
            "summary": (
                "L LINE CORRIDOR CONTEXT\n\n"
                "Stations Brooklyn to Manhattan (the dead-zone stretch):\n"
                "• Bedford Av (J/M/Z connect 5-min walk)\n"
                "• 1st Av (M14 SBS bus connect)\n"
                "• 3rd Av (M101/M102/M103 bus)\n"
                "• Union Sq–14 St (massive transfer hub)\n\n"
                "Service history:\n"
                "• Canarsie Tunnel rebuilt 2019–2020 after Sandy damage\n"
                "• Current 'shutdown' fears reduced — incremental work continues nights/weekends\n"
                "• Weekend service changes COMMON — check before Friday PM rush\n\n"
                "When back online: Brooklyn Magazine (Williamsburg news), amNewYork Transit, MTA twitter @NYCTSubway"
            ),
            "sources": [
                {"url": "https://www.bkmag.com/", "title": "Brooklyn Magazine (online)", "snippet": "Reference: Williamsburg/N. Brooklyn news."},
            ],
        },
    },

    "transbay tube": {
        "road": {
            "summary": (
                "BART TRANSBAY TUBE (Embarcadero SF ↔ West Oakland)\n"
                "• 3.6 mi underwater tunnel, opened 1974\n"
                "• Deepest point: 135 ft below SF Bay water\n"
                "• Run time Embarcadero ↔ West Oakland: ~7 min, no intermediate stops\n"
                "• ZERO cell service in tube. Reconnects at Embarcadero or West Oakland.\n"
                "• Service: 6 lines run through tube (Yellow/Red/Blue/Green/Orange + Coliseum-OAK)\n"
                "• Headways: 5 min peak, 10–15 min off-peak, 20 min nights\n"
                "• Service ends ~midnight weeknights, ~1 AM weekends\n\n"
                "TRANSFERS:\n"
                "• Embarcadero (SF): Muni Metro, F-Market streetcar, Ferry Building\n"
                "• West Oakland: AC Transit transbay buses\n\n"
                "IF STUCK IN TUBE:\n"
                "• Stay on train. Tube is engineered to handle most emergencies.\n"
                "• Emergency intercom on each car (red button).\n"
                "• BART Police: (510) 464-7000 (works above ground)"
            ),
            "sources": [
                {"url": "https://www.bart.gov/schedules/advisories", "title": "BART Service Advisories (online)", "snippet": "Reference: live delays when reconnected."},
            ],
        },
        "news": {
            "summary": (
                "BAY AREA TRANSIT CONTEXT\n\n"
                "• Tube was closed nights for seismic retrofit 2019–2024\n"
                "• Bay Bridge closures cascade to BART tube overcrowding\n"
                "• Giants games (Oracle Park, near Embarcadero) = packed trains 7–11 PM\n"
                "• Warriors games (Chase Center) = packed trains via Embarcadero\n"
                "• Last train from SF: ~11:40 PM weekdays, ~12:10 AM Fri-Sat\n\n"
                "When back online: SF Chronicle Transportation, BART Twitter @SFBART, 511 SF Bay app"
            ),
            "sources": [
                {"url": "https://www.sfchronicle.com/transportation/", "title": "SF Chronicle Transportation (online)", "snippet": "Reference: Bay Area transit coverage."},
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
    """Map a query to one of: weather / road / poi / news / emergency.

    Uses WORD-boundary matching for single-word keywords so that:
      - "rain" doesn't match inside "train"
      - "fog" doesn't match inside "Fogtown"
      - "wind" doesn't match inside "Windsor"
    Multi-word keywords (e.g. "rest stop", "service alert") still use
    substring matching since they're unambiguous.

    Check specific topic words (news, rest stops, weather) BEFORE
    generic road/tunnel/transit words.
    """
    import re
    tokens = set(re.findall(r"[a-z0-9]+", q))

    def has_word(*words: str) -> bool:
        return any(w in tokens for w in words)

    def has_phrase(*phrases: str) -> bool:
        return any(p in q for p in phrases)

    # Emergency markers
    if has_phrase("search rescue", "search and rescue") or has_word(
        "emergency", "sheriff", "rescue", "evacuate", "evac", "911", "sar"
    ):
        return "emergency"

    # News markers
    if has_phrase("local news", "regional news") or has_word(
        "news", "incident", "headline", "headlines"
    ):
        return "news"

    # POI / services markers
    if has_phrase(
        "gas station", "gas stations", "rest stop", "rest stops", "rest area",
        "rest areas", "nearby services", "nearby exits", "services exits",
        "hot springs", "service area",
    ) or has_word(
        "fuel", "lodge", "lodging", "restaurant", "restaurants", "food", "cafe",
        "diner", "stop", "stops",
    ):
        return "poi"

    # Weather markers
    if has_word(
        "weather", "forecast", "storm", "storms", "wind", "winds", "rain",
        "snow", "snowing", "fog", "foggy", "temperature", "temperatures",
        "visibility", "humidity",
    ):
        return "weather"

    # Road / transit markers — checked last.
    if has_phrase(
        "road condition", "road conditions", "service alert", "service alerts",
        "service advisory", "service advisories", "traffic advisory",
    ) or has_word(
        "traffic", "construction", "closure", "closures", "delay", "delays",
        "transit", "subway", "bart", "train", "trains", "dot", "highway",
        "tube", "tunnel", "advisory", "advisories",
    ):
        return "road"

    # Fallback: news is the safest generic.
    return "news"


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
