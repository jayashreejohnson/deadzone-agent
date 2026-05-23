"""Nimble web-search wrapper with deterministic stub fallback for demo reliability."""
from __future__ import annotations
import os
import httpx
from bus import emit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

NIMBLE_URL = "https://api.webit.live/api/v1/realtime/serp"  # TODO: confirm shape with docs
_API_KEY = os.getenv("NIMBLE_API_KEY", "").strip()


_STUB_CORPUS = {
    "weather": {
        "summary": "Partly cloudy, 58°F. Light winds, no precipitation expected in the next 6 hours. "
                   "Overnight low 41°F with clear skies — good driving conditions.",
        "sources": [
            {"url": "https://forecast.weather.gov/MapClick.php?lat=44.12&lon=-73.45",
             "title": "NWS — Adirondack region forecast",
             "snippet": "Partly cloudy through Thursday. Highs in the upper 50s, lows near 40."},
            {"url": "https://www.weather.com/weather/today/l/Lake+George+NY",
             "title": "Weather.com — Lake George, NY",
             "snippet": "No precipitation, visibility 10+ miles, winds 5–8 mph from the NW."},
        ],
    },
    "road": {
        "summary": "I-87 northbound clear through Exit 24. Minor construction near Exit 28 (single lane, "
                   "~5 min delay). Route 9N reported clear. No active road closures.",
        "sources": [
            {"url": "https://511ny.org/list/incidents/region/north-country",
             "title": "NY511 — North Country traffic incidents",
             "snippet": "1 active work zone on I-87 NB near MM 96. No closures."},
            {"url": "https://www.dot.ny.gov/regional-offices/region1",
             "title": "NYSDOT Region 1 — current advisories",
             "snippet": "Routine maintenance only. No weather-related closures."},
        ],
    },
    "poi": {
        "summary": "Three notable stops within 20 miles: Stewart's Shops (open 24h, fuel + coffee), "
                   "Adirondack Welcome Center (rest area, restrooms), and Schroon Lake Diner "
                   "(open until 9pm, cash preferred).",
        "sources": [
            {"url": "https://www.stewartsshops.com/locations",
             "title": "Stewart's Shops — Schroon Lake",
             "snippet": "24-hour fuel, hot food, ATM. Exit 28 off I-87."},
            {"url": "https://visitadirondacks.com/places-to-go/welcome-centers",
             "title": "Adirondack Welcome Center",
             "snippet": "Rest area with restrooms, info desk, picnic tables. Exit 18."},
        ],
    },
    "news": {
        "summary": "Local headlines: Lake George Winter Festival opens Saturday. Adirondack Park "
                   "Agency approved new trail markers along Route 9N. No incidents reported.",
        "sources": [
            {"url": "https://www.poststar.com/news/local",
             "title": "The Post-Star — Local news",
             "snippet": "Winter festival schedule released; events run Friday through Sunday."},
            {"url": "https://www.adirondackalmanack.com/",
             "title": "Adirondack Almanack",
             "snippet": "APA approves trail-marker update on 9N corridor."},
        ],
    },
}


def _stub_for(query: str) -> dict:
    q = query.lower()
    if "weather" in q:
        key = "weather"
    elif "road" in q or "traffic" in q or "construction" in q:
        key = "road"
    elif "poi" in q or "point of interest" in q or "stop" in q or "food" in q or "gas" in q:
        key = "poi"
    else:
        key = "news"
    base = _STUB_CORPUS[key]
    return {"query": query, "summary": base["summary"], "sources": base["sources"]}


@tool(name="nimble_search")
async def search(query: str) -> dict:
    """Web search via Nimble. Returns {query, summary, sources}. Falls back to stub on any failure."""
    await emit({"type": "tool", "name": "nimble", "query": query})
    if not _API_KEY:
        result = _stub_for(query)
        LLMObs.annotate(
            input_data=query,
            output_data=result["summary"],
            metadata={"backend": "stub", "source_count": len(result["sources"])},
            tags={"tool": "nimble_search"},
        )
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
        for item in organic[:4]:
            sources.append({
                "url": item.get("url") or item.get("link") or "",
                "title": item.get("title") or item.get("displayed_title") or "",
                "snippet": item.get("snippet") or item.get("description") or "",
            })
        if not sources:
            result = _stub_for(query)
        else:
            summary = " ".join(s["snippet"] for s in sources[:2]) or _stub_for(query)["summary"]
            result = {"query": query, "summary": summary, "sources": sources}
        LLMObs.annotate(
            input_data=query,
            output_data=result["summary"],
            metadata={"backend": "nimble", "source_count": len(result["sources"])},
            tags={"tool": "nimble_search"},
        )
        return result
    except Exception as e:
        await emit({"type": "log", "level": "warn",
                    "msg": f"nimble failed ({e!s}); using stub"})
        result = _stub_for(query)
        LLMObs.annotate(
            input_data=query,
            output_data=result["summary"],
            metadata={"backend": "stub_after_error", "error": str(e)},
            tags={"tool": "nimble_search"},
        )
        return result
