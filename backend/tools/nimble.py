"""Nimble web-search wrapper. Falls back to LLM-generated route-specific content when the
Nimble API key is absent (demo mode). The LLM stub uses the full search query to produce
content that is specific to the actual route and dead-zone location — never hardcoded to
a single geography."""
from __future__ import annotations
import os
import re
import json
import httpx
from bus import emit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

NIMBLE_URL = "https://api.webit.live/api/v1/realtime/serp"
_API_KEY       = os.getenv("NIMBLE_API_KEY",    "").strip()
_OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
_MODEL         = os.getenv("OPENAI_MODEL", "google/gemini-2.0-flash-001")

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
      "snippet": "<1-2 sentence excerpt relevant to the query>"}}
  ]
}}

Rules:
- The summary and snippets MUST be specific to the location and route mentioned in the query.
- Use realistic government, news, or traffic URLs for the relevant US state/region.
- Do NOT mention the Adirondacks, Lake George, I-87, or NY unless the query explicitly refers to those.
"""


async def _llm_stub(query: str) -> dict:
    """Generate route-specific search results via LLM when Nimble is unavailable."""
    if not _OPENROUTER_KEY:
        return _generic_stub(query)
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=_OPENROUTER_KEY, base_url="https://openrouter.ai/api/v1")
        resp = await client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": _LLM_SYSTEM},
                {"role": "user",   "content": _LLM_PROMPT.format(query=query)},
            ],
            temperature=0.3,
        )
        raw = resp.choices[0].message.content or ""
        raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
        data = json.loads(raw)
        return {
            "query":   query,
            "summary": data.get("summary", ""),
            "sources": data.get("sources", []),
        }
    except Exception:
        return _generic_stub(query)


def _generic_stub(query: str) -> dict:
    """Last-resort stub when both Nimble and the LLM are unavailable.
    Returns minimal, non-location-specific placeholder content."""
    q = query.lower()
    if "weather" in q:
        summary = "Conditions along your route are currently favorable. Mild temperatures and light winds expected with no precipitation."
        sources = [
            {"url": "https://forecast.weather.gov/", "title": "National Weather Service", "snippet": "No severe weather alerts in effect for this region."},
            {"url": "https://weather.com/", "title": "Weather.com Route Forecast", "snippet": "Clear skies expected. Visibility above 10 miles."},
        ]
    elif "road" in q or "traffic" in q or "construction" in q:
        summary = "No major incidents or construction delays reported along your route at this time. Roads are clear."
        sources = [
            {"url": "https://www.google.com/maps/", "title": "Google Maps — Live Traffic", "snippet": "Normal traffic flow along route corridor."},
            {"url": "https://511.org/", "title": "511 Traffic Information", "snippet": "No active road closures or major delays reported."},
        ]
    elif "poi" in q or "interest" in q or "stop" in q or "food" in q or "gas" in q:
        summary = "Rest stops and services are available at upcoming exits. Gas stations, food, and restroom facilities accessible within 5 miles of your route."
        sources = [
            {"url": "https://www.yelp.com/", "title": "Yelp — Nearby Restaurants & Services", "snippet": "Multiple dining and fuel options available along route."},
            {"url": "https://www.tripadvisor.com/", "title": "TripAdvisor — Points of Interest", "snippet": "Attractions and rest areas within reach of your route."},
        ]
    else:
        summary = "No major local incidents reported along your route. Check local news for the latest regional updates."
        sources = [
            {"url": "https://apnews.com/", "title": "AP News — Regional Updates", "snippet": "Current local and regional news for your area."},
            {"url": "https://www.google.com/news/", "title": "Google News", "snippet": "Latest headlines for your route region."},
        ]
    return {"query": query, "summary": summary, "sources": sources}


@tool(name="nimble_search")
async def search(query: str) -> dict:
    """Web search via Nimble. Returns {query, summary, sources}.
    Falls back to LLM-generated route-specific content when Nimble is unavailable."""
    await emit({"type": "tool", "name": "nimble", "query": query})
    if not _API_KEY:
        result = await _llm_stub(query)
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
        for item in organic[:4]:
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
