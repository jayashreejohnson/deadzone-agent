"""LLM-driven orchestrator using OpenAI function calling.

The LLM decides which tools to invoke and in what order. Each tool wrapper emits a
WebSocket event when called, so the UI streams the agent's reasoning live.

If OPENAI_API_KEY is missing, falls back to a deterministic hardcoded sequence so the
demo still runs end-to-end.

Pattern: https://developers.openai.com/api/docs/guides/function-calling
"""
from __future__ import annotations
import os
import json
import asyncio
import time
import uuid
from typing import Any

from bus import emit
from tools import nimble, senso, payments, clickhouse_db as db
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import workflow, agent

_OPENAI_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
_MODEL = os.getenv("OPENAI_MODEL", "google/gemini-2.0-flash-001")

PRICE_USD = 0.02


# ---------- Tool schemas exposed to the LLM ----------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "clickhouse_find_recent_pack",
            "description": (
                "Look up a recently-built offline pack for this exact route+deadzone. "
                "Call this FIRST before doing any web search. If a pack is returned, "
                "the user's agent should buy it instead of rebuilding."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "route_id": {"type": "string"},
                    "deadzone_id": {"type": "string"},
                    "max_age_min": {"type": "integer", "default": 10},
                },
                "required": ["route_id", "deadzone_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "nimble_search",
            "description": (
                "Web search for one specific topic. Call this 4 times in parallel for: "
                "weather forecast, road conditions, points of interest, local news. "
                "Returns summary + citation sources."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural-language search query"},
                    "topic": {
                        "type": "string",
                        "enum": ["weather", "road", "poi", "news"],
                        "description": "Which section this result will fill",
                    },
                },
                "required": ["query", "topic"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "senso_publish",
            "description": (
                "Publish the assembled pack to a public URL (cited.md), preserving citations. "
                "Call this AFTER nimble_search has returned for all four topics. "
                "Pass the search results as sections."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "route_id": {"type": "string"},
                    "sections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "heading": {"type": "string"},
                                "summary": {"type": "string"},
                                "sources": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "url": {"type": "string"},
                                            "title": {"type": "string"},
                                            "snippet": {"type": "string"},
                                        },
                                        "required": ["url", "title", "snippet"],
                                        "additionalProperties": False,
                                    },
                                },
                            },
                            "required": ["heading", "summary", "sources"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["title", "route_id", "sections"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clickhouse_save_pack",
            "description": "Persist a newly-built pack so future drivers can buy it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "route_id": {"type": "string"},
                    "deadzone_id": {"type": "string"},
                    "url": {"type": "string"},
                    "owner_user_id": {"type": "string"},
                    "source_count": {"type": "integer"},
                },
                "required": ["route_id", "deadzone_id", "url", "owner_user_id", "source_count"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "payments_pay",
            "description": (
                "Agent-to-agent x402 payment. Call this when the user is BUYING an existing "
                "cached pack — pay the original owner."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "from_agent": {"type": "string"},
                    "to_agent": {"type": "string"},
                    "amount_usd": {"type": "number"},
                    "memo": {"type": "string"},
                },
                "required": ["from_agent", "to_agent", "amount_usd", "memo"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clickhouse_log_event",
            "description": "Telemetry. Call this once at the end with action='built' or 'bought'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "route_id": {"type": "string"},
                    "deadzone_id": {"type": "string"},
                    "action": {"type": "string", "enum": ["built", "bought", "delivered"]},
                    "pack_id": {"type": "string"},
                    "build_ms": {"type": "integer"},
                },
                "required": ["user_id", "route_id", "deadzone_id", "action", "pack_id", "build_ms"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deliver_pack",
            "description": (
                "Final step: notify the user that the pack is ready. Call this last, "
                "with the public URL and whether it was a cache hit."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "cached": {"type": "boolean"},
                    "pack_id": {"type": "string"},
                },
                "required": ["url", "cached", "pack_id"],
                "additionalProperties": False,
            },
        },
    },
]


# ---------- Tool dispatcher ----------
class _Ctx:
    """Mutable shared state across one orchestration run (timings, pack_id, etc)."""
    def __init__(self, signal: dict):
        self.signal = signal
        self.t0 = time.time()
        self.pack_id: str = ""
        self.pack_url: str = ""
        self.cached: bool = False
        self.last_payment_tx: str | None = None
        self.delivered: bool = False


async def _dispatch(name: str, args: dict, ctx: _Ctx) -> Any:
    if name == "clickhouse_find_recent_pack":
        row = db.find_recent_pack(args["route_id"], args["deadzone_id"], args.get("max_age_min", 10))
        return {"found": bool(row), "pack": _pack_to_dict(row) if row else None}

    if name == "nimble_search":
        result = await nimble.search(args["query"])
        result["topic"] = args["topic"]
        return result

    if name == "senso_publish":
        url = await senso.publish(args["title"], args["route_id"], args["sections"])
        ctx.pack_url = url
        return {"url": url}

    if name == "clickhouse_save_pack":
        pid = db.save_pack(
            args["route_id"], args["deadzone_id"], args["url"],
            args["owner_user_id"], args["source_count"],
        )
        ctx.pack_id = pid
        return {"pack_id": pid}

    if name == "payments_pay":
        result = await payments.pay(
            args["from_agent"], args["to_agent"], args["amount_usd"], args.get("memo", ""),
        )
        ctx.last_payment_tx = result["tx_id"]
        db.log_payment(result["tx_id"], args["from_agent"], args["to_agent"],
                       args["amount_usd"], ctx.pack_id)
        return result

    if name == "clickhouse_log_event":
        db.log_event(
            args["user_id"], args["route_id"], args["deadzone_id"], args["action"],
            args.get("pack_id", ""), args.get("build_ms", 0),
        )
        return {"ok": True}

    if name == "deliver_pack":
        ctx.pack_url = args["url"]
        ctx.cached = args["cached"]
        if args.get("pack_id"):
            ctx.pack_id = args["pack_id"]
        ctx.delivered = True
        await emit({"type": "pack_ready", "url": args["url"],
                    "cached": args["cached"], "pack_id": ctx.pack_id})
        return {"ok": True}

    return {"error": f"unknown tool: {name}"}


def _pack_to_dict(p: dict) -> dict:
    return {
        "pack_id": p["pack_id"], "route_id": p["route_id"],
        "deadzone_id": p["deadzone_id"], "url": p["url"],
        "owner_user_id": p["owner_user_id"],
        "source_count": p["source_count"],
    }


# ---------- Entry point ----------
@workflow(name="deadzone_signal")
async def run(signal: dict) -> None:
    """Orchestrate one dead-zone signal end-to-end."""
    eta = signal.get("eta_seconds", 240)
    await emit({"type": "status",
                "msg": f"Dead zone in {eta // 60} min — preparing pack",
                "user_id": signal["user_id"]})
    try:
        LLMObs.annotate(
            input_data=signal,
            metadata={"path": "llm" if _OPENAI_KEY else "scripted_fallback", "model": _MODEL},
            tags={"workflow": "deadzone_signal", "user_id": signal["user_id"],
                  "route_id": signal["route_id"], "deadzone_id": signal["deadzone_id"]},
        )
    except Exception:
        pass  # LLMObs disabled — no-op

    if _OPENAI_KEY:
        try:
            await _run_with_llm(signal)
            return
        except Exception as e:
            await emit({"type": "log", "level": "warn",
                        "msg": f"LLM orchestrator failed ({e!s}); falling back to scripted flow"})
    await _run_scripted(signal)


# ---------- LLM-driven path ----------
SYSTEM_PROMPT = """You are an offline-pack-building agent. A user is approaching a connectivity dead zone and needs an offline content pack delivered BEFORE they lose signal — time matters.

Workflow (follow exactly):

1. Call `clickhouse_find_recent_pack` first with the route_id and deadzone_id from the signal.

2A. IF a pack is found (cache hit):
    - Call `payments_pay` from the user's agent to the cached pack's owner_user_id (use "agent_<last_letter_of_user_id>" naming — e.g. user_a → agent_a, user_b → agent_b). Amount: 0.02 USD. Memo: "buy cached pack".
    - Call `clickhouse_log_event` with action="bought", the found pack_id, build_ms=0.
    - Call `deliver_pack` with the cached URL, cached=true, the pack_id.
    - Reply with one short sentence and stop.

2B. IF no pack is found (cache miss):
    - Call `nimble_search` FOUR TIMES IN PARALLEL — one for each topic:
        * topic="weather", query about weather near the lat/lng
        * topic="road",    query about road conditions on this route
        * topic="poi",     query about points of interest near the lat/lng
        * topic="news",    query about local news near the lat/lng
    - Call `senso_publish` with title like "Offline pack: <route>", route_id, and a `sections` array — one section per search result with heading ("Weather", "Road conditions", "Points of interest", "Local news"), summary (the search summary), and sources (the search sources).
    - Call `clickhouse_save_pack` with the returned URL, owner_user_id from the signal, source_count = total sources across all sections. THIS RETURNS a pack_id — you MUST use the EXACT pack_id string it returns (looks like "pk_xxxxxxx") in all subsequent calls. Do not invent or substitute a placeholder.
    - Call `clickhouse_log_event` with action="built", pack_id = the EXACT pack_id returned by clickhouse_save_pack, build_ms=0.
    - Call `deliver_pack` with the new URL, cached=false, pack_id = the EXACT pack_id returned by clickhouse_save_pack.
    - Reply with one short sentence and stop.

Be fast. Issue parallel tool calls whenever possible. Do not invent data — use the tools."""


@agent(name="pack_builder")
async def _run_with_llm(signal: dict) -> None:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=_OPENAI_KEY, base_url="https://openrouter.ai/api/v1")
    ctx = _Ctx(signal)
    try:
        LLMObs.annotate(
            input_data=signal,
            metadata={"model": _MODEL, "tools_available": [t["function"]["name"] for t in TOOLS]},
            tags={"agent": "pack_builder"},
        )
    except Exception:
        pass  # LLMObs disabled — no-op

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content":
            f"Signal received:\n{json.dumps(signal, indent=2)}\n\n"
            f"Execute the workflow now."},
    ]

    for _ in range(8):  # safety cap on tool-loop iterations
        resp = await client.chat.completions.create(
            model=_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            parallel_tool_calls=True,
            temperature=0,
        )
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        tool_calls = msg.tool_calls or []
        if not tool_calls:
            break  # LLM returned plain text — done

        # Run tool calls (in parallel where the LLM requested it).
        async def _exec(tc):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}
            try:
                result = await _dispatch(tc.function.name, args, ctx)
            except Exception as exc:
                await emit({"type": "log", "level": "warn",
                            "msg": f"tool {tc.function.name} raised: {exc!s}"})
                result = {"error": str(exc)}
            return tc.id, tc.function.name, result

        results = await asyncio.gather(*[_exec(tc) for tc in tool_calls], return_exceptions=False)
        for tc_id, name, result in results:
            messages.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "name": name,
                "content": json.dumps(result, default=str),
            })

        if ctx.delivered:
            # One more turn to let the model produce its final text, then we're done.
            final = await client.chat.completions.create(
                model=_MODEL, messages=messages, temperature=0,
            )
            await emit({"type": "log", "level": "info",
                        "msg": f"agent: {final.choices[0].message.content or 'done'}"})
            return


# ---------- Hardcoded fallback path (no API key) ----------
async def _run_scripted(signal: dict) -> None:
    ctx = _Ctx(signal)
    route_id = signal["route_id"]
    deadzone_id = signal["deadzone_id"]
    user_id = signal["user_id"]
    buyer_agent = "agent_" + user_id.split("_")[-1]

    cached = db.find_recent_pack(route_id, deadzone_id)
    if cached:
        seller_agent = "agent_" + cached["owner_user_id"].split("_")[-1]
        await emit({"type": "log", "level": "info", "msg": "cache hit — buying pack"})
        try:
            result = await payments.pay(buyer_agent, seller_agent, PRICE_USD, "buy cached pack")
            db.log_payment(result["tx_id"], buyer_agent, seller_agent, PRICE_USD, cached["pack_id"])
        except Exception as e:
            await emit({"type": "log", "level": "warn",
                        "msg": f"payment failed ({e!s}); delivering pack anyway"})
        db.log_event(user_id, route_id, deadzone_id, "bought", cached["pack_id"], 0)
        await emit({"type": "pack_ready", "url": cached["url"],
                    "cached": True, "pack_id": cached["pack_id"]})
        return

    queries = [
        ("weather", f"weather forecast near {signal['lat']:.3f},{signal['lng']:.3f}"),
        ("road",    f"road conditions on route {route_id}"),
        ("poi",     f"points of interest near {signal['lat']:.3f},{signal['lng']:.3f}"),
        ("news",    f"local news near {signal['lat']:.3f},{signal['lng']:.3f}"),
    ]
    try:
        results = await asyncio.gather(*[nimble.search(q) for _, q in queries])
    except Exception as e:
        await emit({"type": "log", "level": "error",
                    "msg": f"nimble search failed ({e!s}); aborting build"})
        return
    headings = {"weather": "Weather", "road": "Road conditions",
                "poi": "Points of interest", "news": "Local news"}
    sections = [{
        "heading": headings[topic],
        "summary": r["summary"],
        "sources": r["sources"],
    } for (topic, _), r in zip(queries, results)]
    source_count = sum(len(s["sources"]) for s in sections)

    try:
        url = await senso.publish(f"Offline pack: {route_id}", route_id, sections)
    except Exception as e:
        await emit({"type": "log", "level": "error",
                    "msg": f"senso publish failed ({e!s}); aborting build"})
        return
    try:
        pack_id = db.save_pack(route_id, deadzone_id, url, user_id, source_count)
    except Exception as e:
        await emit({"type": "log", "level": "error",
                    "msg": f"save_pack failed ({e!s}); delivering pack without DB record"})
        pack_id = "pk_nosave_" + uuid.uuid4().hex[:8]
    build_ms = int((time.time() - ctx.t0) * 1000)
    db.log_event(user_id, route_id, deadzone_id, "built", pack_id, build_ms)
    await emit({"type": "pack_ready", "url": url, "cached": False, "pack_id": pack_id})

