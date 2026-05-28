"""LLM-driven orchestrator using OpenAI function calling.

Features:
- Correlation IDs (trace_id) threaded through every event
- Execution Waterfall: tool_start / tool_end events with ms timing
- Pack Quality Eval: async scorer after delivery (coverage, SLA, completion)
- Replay: all events stored in clickhouse_db._traces for /replay/{trace_id}

If OPENAI_API_KEY is missing, falls back to a deterministic hardcoded sequence.
"""
from __future__ import annotations
import os
import json
import asyncio
import time
import uuid
from typing import Any

from bus import emit
from tools import nimble, senso, payments, clickhouse_db as db, llm_circuit
from tools.agent1 import is_transit_route
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import workflow, agent

_OPENROUTER_KEY   = os.getenv("OPENROUTER_API_KEY", "").strip()
_OPENROUTER_MODEL = os.getenv("OPENAI_MODEL",       "google/gemini-2.0-flash-001").strip()
_GROQ_KEY         = os.getenv("GROQ_API_KEY",       "").strip()
_GROQ_MODEL       = os.getenv("GROQ_MODEL",         "llama-3.3-70b-versatile").strip()
_CEREBRAS_KEY     = os.getenv("CEREBRAS_API_KEY",   "").strip()
_CEREBRAS_MODEL   = os.getenv("CEREBRAS_MODEL",     "llama-3.3-70b").strip()

# Short per-request timeout so a dead provider doesn't burn 30s before
# we try the next one in the chain.
_LLM_TIMEOUT_SEC  = float(os.getenv("LLM_TIMEOUT_SEC", "8"))

# Pick the active provider — OpenRouter primary, Groq fallback, Cerebras final.
# Set _LLM_PROVIDER, _LLM_KEY, _LLM_BASE_URL, _LLM_MODEL at import time so the
# rest of this module can stay simple.
if _OPENROUTER_KEY:
    _LLM_PROVIDER = "openrouter"
    _LLM_KEY      = _OPENROUTER_KEY
    _LLM_BASE_URL = "https://openrouter.ai/api/v1"
    _LLM_MODEL    = _OPENROUTER_MODEL
elif _GROQ_KEY:
    _LLM_PROVIDER = "groq"
    _LLM_KEY      = _GROQ_KEY
    _LLM_BASE_URL = "https://api.groq.com/openai/v1"
    _LLM_MODEL    = _GROQ_MODEL
elif _CEREBRAS_KEY:
    _LLM_PROVIDER = "cerebras"
    _LLM_KEY      = _CEREBRAS_KEY
    _LLM_BASE_URL = "https://api.cerebras.ai/v1"
    _LLM_MODEL    = _CEREBRAS_MODEL
else:
    _LLM_PROVIDER = ""
    _LLM_KEY      = ""
    _LLM_BASE_URL = ""
    _LLM_MODEL    = ""

# Back-compat for the gating check below.
_OPENAI_KEY = _LLM_KEY
_MODEL      = _LLM_MODEL

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
                "Call this AFTER nimble_search has returned for all four topics."
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


# ---------- Shared execution context ----------

class _Ctx:
    """Mutable shared state across one orchestration run."""
    def __init__(self, signal: dict):
        self.signal       = signal
        self.t0           = time.time()
        self.trace_id     = f"tr_{uuid.uuid4().hex[:12]}"
        self.pack_id:     str = ""
        self.pack_url:    str = ""
        self.cached:      bool = False
        self.last_payment_tx: str | None = None
        self.delivered:   bool = False
        self.event_logged: bool = False
        self.tools_called: set[str] = set()
        self.tool_errors:  list[str] = []
        self._tool_seq:   int = 0  # monotonic call_id counter for waterfall


def _now_ms(ctx: _Ctx) -> int:
    return int((time.time() - ctx.t0) * 1000)


# ---------- Core tool dispatcher ----------

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
        if not ctx.event_logged:
            db.log_event(
                args["user_id"], args["route_id"], args["deadzone_id"], args["action"],
                args.get("pack_id", ""), args.get("build_ms", 0),
            )
            ctx.event_logged = True
        return {"ok": True}

    if name == "deliver_pack":
        ctx.pack_url  = args["url"]
        ctx.cached    = args["cached"]
        if args.get("pack_id"):
            ctx.pack_id = args["pack_id"]
        ctx.delivered = True
        if not ctx.event_logged:
            build_ms = _now_ms(ctx)
            action = "bought" if ctx.cached else "built"
            db.log_event(
                ctx.signal["user_id"], ctx.signal["route_id"],
                ctx.signal["deadzone_id"], action,
                ctx.pack_id, build_ms if action == "built" else 0,
            )
            ctx.event_logged = True
        pack_ev = {
            "type":       "pack_ready",
            "url":        args["url"],
            "cached":     args["cached"],
            "pack_id":    ctx.pack_id,
            "deadzone_id": ctx.signal.get("deadzone_id", ""),
            "route_id":   ctx.signal.get("route_id", ""),
            "route":      ctx.signal.get("route", ""),
            "trace_id":   ctx.trace_id,
            "t_ms":       _now_ms(ctx),
        }
        await emit(pack_ev)
        db.append_trace_event(ctx.trace_id, pack_ev)
        return {"ok": True}

    return {"error": f"unknown tool: {name}"}


# ---------- Waterfall-timed dispatcher ----------

async def _timed_dispatch(name: str, args: dict, ctx: _Ctx) -> Any:
    """Emit tool_start / tool_end timing events and store to trace for waterfall + replay."""
    ctx.tools_called.add(name)
    call_id = ctx._tool_seq
    ctx._tool_seq += 1
    t_ms = _now_ms(ctx)

    start_ev = {
        "type": "tool_start", "tool": name, "call_id": call_id,
        "t_ms": t_ms, "trace_id": ctx.trace_id,
    }
    await emit(start_ev)
    db.append_trace_event(ctx.trace_id, start_ev)

    t_wall = time.time()
    error: str | None = None
    result: Any = None
    try:
        result = await _dispatch(name, args, ctx)
    except Exception as exc:
        error = str(exc)
        result = {"error": error}
        ctx.tool_errors.append(f"{name}: {error}")

    latency_ms = int((time.time() - t_wall) * 1000)
    end_ev = {
        "type": "tool_end", "tool": name, "call_id": call_id,
        "t_ms": t_ms, "latency_ms": latency_ms,
        "trace_id": ctx.trace_id, "ok": error is None,
    }
    await emit(end_ev)
    db.append_trace_event(ctx.trace_id, end_ev)

    # Reconstruct inner sub-events in trace so replay shows same log lines as live
    if error is None:
        sub_t = t_ms + 2
        if name == "nimble_search":
            db.append_trace_event(ctx.trace_id, {
                "type": "tool", "name": "nimble", "query": args.get("query", ""),
                "t_ms": sub_t, "trace_id": ctx.trace_id,
            })
        elif name == "senso_publish":
            db.append_trace_event(ctx.trace_id, {
                "type": "tool", "name": "senso",
                "msg": f"Publishing pack: {args.get('title', '')}",
                "t_ms": sub_t, "trace_id": ctx.trace_id,
            })
        elif name == "payments_pay" and isinstance(result, dict):
            db.append_trace_event(ctx.trace_id, {
                "type": "payment",
                "amount": args.get("amount_usd", 0),
                "from": args.get("from_agent", ""),
                "to": args.get("to_agent", ""),
                "tx": result.get("tx_id", ""),
                "t_ms": sub_t, "trace_id": ctx.trace_id,
            })

    return result


# ---------- Pack quality evaluator ----------

async def _eval_pack(ctx: _Ctx) -> None:
    """Run after delivery — emits eval_complete with coverage, SLA, and quality score."""
    build_ms = _now_ms(ctx)
    eta_ms   = ctx.signal.get("eta_seconds", 240) * 1000

    CATEGORIES: list[set[str]] = [
        {"nimble_search"},
        {"senso_publish"},
        {"clickhouse_save_pack", "clickhouse_find_recent_pack"},
        {"deliver_pack"},
    ]
    covered    = sum(1 for cat in CATEGORIES if cat & ctx.tools_called) / len(CATEGORIES)
    sla_pass   = build_ms < eta_ms * 0.85
    complete   = "deliver_pack" in ctx.tools_called and not ctx.tool_errors

    # Penalty: each tool error deducts 5 points; errors cap score at 70
    error_penalty = min(len(ctx.tool_errors) * 5, 30)

    raw_score = int(
        (covered * 0.4 + (1.0 if sla_pass else 0.0) * 0.4 + (1.0 if complete else 0.0) * 0.2) * 100
    )
    score = max(0, raw_score - error_penalty)

    ev = {
        "type":         "eval_complete",
        "trace_id":     ctx.trace_id,
        "score":        score,
        "coverage":     round(covered, 2),
        "sla_pass":     sla_pass,
        "complete":     complete,
        "build_ms":     build_ms,
        "tools_called": sorted(ctx.tools_called),
        "t_ms":         build_ms,
    }
    await emit(ev)
    db.append_trace_event(ctx.trace_id, ev)


def _pack_to_dict(p: dict) -> dict:
    return {
        "pack_id": p["pack_id"], "route_id": p["route_id"],
        "deadzone_id": p["deadzone_id"], "url": p["url"],
        "owner_user_id": p["owner_user_id"], "source_count": p["source_count"],
    }


# ---------- Entry point ----------

@workflow(name="deadzone_signal")
async def run(signal: dict) -> None:
    """Orchestrate one dead-zone signal end-to-end."""
    ctx = _Ctx(signal)
    eta = signal.get("eta_seconds", 240)

    # Broadcast trace identity so frontend can correlate all events
    trace_ev = {
        "type":       "trace_started",
        "trace_id":   ctx.trace_id,
        "user_id":    signal["user_id"],
        "deadzone_id": signal.get("deadzone_id", ""),
        "t_ms":       0,
    }
    await emit(trace_ev)
    db.append_trace_event(ctx.trace_id, trace_ev)

    status_ev = {
        "type":     "status",
        "msg":      f"Dead zone in {eta // 60}m {eta % 60:02d}s — preparing pack",
        "user_id":  signal["user_id"],
        "trace_id": ctx.trace_id,
        "t_ms":     _now_ms(ctx),
    }
    await emit(status_ev)
    db.append_trace_event(ctx.trace_id, status_ev)

    try:
        LLMObs.annotate(
            input_data=signal,
            metadata={"path": "llm" if _OPENAI_KEY else "scripted_fallback", "model": _MODEL},
            tags={"workflow": "deadzone_signal", "user_id": signal["user_id"],
                  "route_id": signal["route_id"], "deadzone_id": signal["deadzone_id"],
                  "trace_id": ctx.trace_id},
        )
    except Exception:
        pass

    # Agentic-first: try the LLM unless the shared circuit breaker is open
    # (i.e. a recent call from anywhere in the stack already proved both
    # providers are down). Once open, skip straight to the scripted path so
    # we don't burn 30s+ on a guaranteed timeout.
    if _OPENAI_KEY and not llm_circuit.is_open():
        try:
            await _run_with_llm(signal, ctx)
            return
        except Exception as e:
            llm_circuit.trip(f"orchestrator:{type(e).__name__}")
            warn_ev = {
                "type": "log", "level": "warn",
                "msg":  f"LLM orchestrator failed ({e!s}); falling back to scripted flow",
                "trace_id": ctx.trace_id, "t_ms": _now_ms(ctx),
            }
            await emit(warn_ev)
            db.append_trace_event(ctx.trace_id, warn_ev)
    elif _OPENAI_KEY and llm_circuit.is_open():
        skip_ev = {
            "type": "log", "level": "warn",
            "msg":  f"LLM circuit open ({llm_circuit.seconds_remaining()}s left); using scripted flow",
            "trace_id": ctx.trace_id, "t_ms": _now_ms(ctx),
        }
        await emit(skip_ev)
        db.append_trace_event(ctx.trace_id, skip_ev)
    await _run_scripted(signal, ctx)


# ---------- LLM-driven path ----------

SYSTEM_PROMPT = """You are an offline-pack-building agent. A user is approaching a connectivity dead zone and needs an offline content pack delivered BEFORE they lose signal — time matters.

The signal dict you receive includes:
- duration_minutes: how long the dead zone lasts (drives content depth)
- severity: "high" | "medium" | "low"
- zone_description: human-readable name of the zone (e.g. "Lincoln Tunnel Mid")
- route: the full route name (e.g. "Manhattan to Newark")
- lat / lng: coordinates of the dead zone

ROUTE TYPE DETECTION — look at the route string and classify it:
- TRANSIT route: contains "train", "subway", "BART", "metro", "transit", "tube", "L train", "E train"
- MOUNTAIN route: contains "Million Dollar Highway", "Vail", "US-550", "PCH", "Big Sur", "mountain", "pass"
- LONG RURAL route: contains "US-50", "Nevada", "loneliest road", duration_minutes >= 15
- URBAN TUNNEL route: "Lincoln Tunnel", "Newark", "Manhattan", "tunnel", subway lines
- DEFAULT: standard highway driving route

Workflow (follow exactly):

1. Call `clickhouse_find_recent_pack` first with the route_id and deadzone_id from the signal.

2A. IF a pack is found (cache hit):
    - Call `payments_pay` from the user's agent to the cached pack's owner_user_id (use "agent_<last_letter_of_user_id>" naming — e.g. user_a → agent_a, user_b → agent_b). Amount: 0.02 USD. Memo: "buy cached pack".
    - Call `clickhouse_log_event` with action="bought", the found pack_id, build_ms=0.
    - Call `deliver_pack` with the cached URL, cached=true, the pack_id.
    - Reply with one short sentence and stop.

2B. IF no pack is found (cache miss), choose queries based on ROUTE TYPE and duration_minutes:

    TRANSIT ROUTE — run nimble_search calls for transit-specific content:
        * topic="road",    query: "{zone_description} {route} transit service alerts delays today"
        * topic="news",    query: "commuter news updates {zone_description} {route}"
        * topic="weather", query: "weather forecast {zone_description}" (if duration >= 5)
        * topic="poi",     query: "nearby services exits {zone_description}" (if duration >= 5)

    MOUNTAIN ROUTE — safety is critical, always 4 searches:
        * topic="weather", query: "high elevation mountain weather {zone_description} {route} forecast alerts"
        * topic="road",    query: "road conditions closures rockslide avalanche {zone_description} {route}"
        * topic="poi",     query: "emergency contacts search rescue services {zone_description} county sheriff"
        * topic="news",    query: "local mountain news road conditions {zone_description} {route}"

    LONG RURAL ROUTE (duration >= 15 min) — scale content for extended blackout:
        * topic="weather", query: "weather forecast next 4 hours {zone_description} {route}"
        * topic="road",    query: "road conditions gas stations services {zone_description} {route}"
        * topic="poi",     query: "last gas station before {zone_description} {route} emergency services"
        * topic="news",    query: "local news {zone_description} {route}"

    URBAN TUNNEL / DEFAULT — standard 4-topic search for long, 3 for medium, 2 for short:
        LONG (duration_minutes >= 5):
            * topic="weather", query: "weather {zone_description} {route}"
            * topic="road",    query: "road conditions traffic {zone_description} {route}"
            * topic="news",    query: "local news {zone_description} {route}"
            * topic="poi",     query: "nearby services rest stops {zone_description} {route}"
        MEDIUM (2–4 min): weather + road + news
        SHORT (< 2 min): road + news

    After all search calls return:
    - Call `senso_publish` with descriptive title and sections.
    - Call `clickhouse_save_pack` with the returned URL, owner_user_id from the signal, source_count = total sources.
    - Call `clickhouse_log_event` with action="built", pack_id = EXACT pack_id from clickhouse_save_pack.
    - Call `deliver_pack` with the new URL, cached=false, exact pack_id.
    - Reply with one short sentence and stop.

CRITICAL RULE: You MUST always call `deliver_pack` as the FINAL tool call in every run.
deliver_pack is MANDATORY — without it the user's device will not receive the pack.
Never finish without calling deliver_pack. This is not optional.

Be fast. Issue parallel tool calls whenever possible. Do not invent data — use the tools."""


async def _call_llm_with_fallback(messages: list[dict], tools: list[dict] | None = None):
    """Try OpenRouter, then Groq. Each request is independent — if OpenRouter
    fails on iteration 3 of the tool loop, iteration 4 can still come back to
    it (rate-limit case). Tool-calling state is just messages, so providers
    are interchangeable."""
    from openai import AsyncOpenAI
    last_error: Exception | None = None

    if _OPENROUTER_KEY:
        try:
            c = AsyncOpenAI(api_key=_OPENROUTER_KEY, base_url="https://openrouter.ai/api/v1", timeout=_LLM_TIMEOUT_SEC)
            kwargs: dict = {"model": _OPENROUTER_MODEL, "messages": messages,
                            "temperature": 0, "max_tokens": 2048}
            if tools:
                kwargs.update({"tools": tools, "tool_choice": "auto", "parallel_tool_calls": True})
            resp = await c.chat.completions.create(**kwargs)
            llm_circuit.reset()
            return resp, "openrouter"
        except Exception as e:
            print(f"[orchestrator] OpenRouter call failed: {type(e).__name__}: {str(e)[:160]}; trying Groq", flush=True)
            last_error = e

    if _GROQ_KEY:
        try:
            c = AsyncOpenAI(api_key=_GROQ_KEY, base_url="https://api.groq.com/openai/v1", timeout=_LLM_TIMEOUT_SEC)
            kwargs = {"model": _GROQ_MODEL, "messages": messages,
                      "temperature": 0, "max_tokens": 2048}
            if tools:
                kwargs.update({"tools": tools, "tool_choice": "auto", "parallel_tool_calls": True})
            resp = await c.chat.completions.create(**kwargs)
            llm_circuit.reset()
            return resp, "groq"
        except Exception as e:
            print(f"[orchestrator] Groq call failed: {type(e).__name__}: {str(e)[:160]}; trying Cerebras", flush=True)
            last_error = e

    if _CEREBRAS_KEY:
        try:
            c = AsyncOpenAI(api_key=_CEREBRAS_KEY, base_url="https://api.cerebras.ai/v1", timeout=_LLM_TIMEOUT_SEC)
            kwargs = {"model": _CEREBRAS_MODEL, "messages": messages,
                      "temperature": 0, "max_tokens": 2048}
            if tools:
                # Cerebras supports OpenAI-style tools, but not parallel_tool_calls on all models.
                # Omit the parallel flag to maximize compatibility.
                kwargs.update({"tools": tools, "tool_choice": "auto"})
            resp = await c.chat.completions.create(**kwargs)
            llm_circuit.reset()
            return resp, "cerebras"
        except Exception as e:
            print(f"[orchestrator] Cerebras call failed: {type(e).__name__}: {str(e)[:160]}", flush=True)
            last_error = e

    # All providers failed for this call — trip the shared breaker.
    llm_circuit.trip(f"orchestrator:{type(last_error).__name__ if last_error else 'no_providers'}")
    raise last_error or RuntimeError("No LLM providers configured")


@agent(name="pack_builder")
async def _run_with_llm(signal: dict, ctx: _Ctx) -> None:
    print(f"[orchestrator] LLM primary={_LLM_PROVIDER} ({_LLM_MODEL}), Groq fallback={'ready' if _GROQ_KEY else 'not configured'}", flush=True)
    try:
        LLMObs.annotate(
            input_data=signal,
            metadata={"model": _MODEL, "tools_available": [t["function"]["name"] for t in TOOLS]},
            tags={"agent": "pack_builder", "trace_id": ctx.trace_id},
        )
    except Exception:
        pass

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content":
            f"Signal received:\n{json.dumps(signal, indent=2)}\n\nExecute the workflow now."},
    ]

    for _ in range(8):
        resp, _provider = await _call_llm_with_fallback(messages, tools=TOOLS)
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        tool_calls = msg.tool_calls or []
        if not tool_calls:
            break

        async def _exec(tc):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}
            result = await _timed_dispatch(tc.function.name, args, ctx)
            if "error" in result:
                warn_ev = {
                    "type": "log", "level": "warn",
                    "msg":  f"tool {tc.function.name}: {result['error']}",
                    "trace_id": ctx.trace_id, "t_ms": _now_ms(ctx),
                }
                await emit(warn_ev)
                db.append_trace_event(ctx.trace_id, warn_ev)
            return tc.id, tc.function.name, result

        results = await asyncio.gather(*[_exec(tc) for tc in tool_calls], return_exceptions=False)
        for tc_id, name, result in results:
            messages.append({
                "role": "tool", "tool_call_id": tc_id,
                "name": name, "content": json.dumps(result, default=str),
            })

        if ctx.delivered:
            zone_desc  = ctx.signal.get("zone_description") or ctx.signal.get("route", "your route")
            cached_str = "cached pack reused" if ctx.cached else "fresh pack assembled"
            final_ev = {
                "type": "log", "level": "info",
                "msg":  f"Delivering {cached_str} for {zone_desc}",
                "trace_id": ctx.trace_id, "t_ms": _now_ms(ctx),
            }
            await emit(final_ev)
            db.append_trace_event(ctx.trace_id, final_ev)
            break

    # Safety net: if the LLM never called deliver_pack, do it now
    if not ctx.delivered and ctx.pack_url:
        warn_ev = {
            "type": "log", "level": "warn",
            "msg":  "LLM did not call deliver_pack; forcing delivery",
            "trace_id": ctx.trace_id, "t_ms": _now_ms(ctx),
        }
        await emit(warn_ev)
        db.append_trace_event(ctx.trace_id, warn_ev)
        await _timed_dispatch("deliver_pack", {
            "url":      ctx.pack_url,
            "cached":   ctx.cached,
            "pack_id":  ctx.pack_id,
        }, ctx)

    await _eval_pack(ctx)


# ---------- Route type helpers ----------

def _is_mountain_route(route: str) -> bool:
    """True for mountain/alpine routes where safety content (emergency contacts, elevation weather) matters."""
    markers = [
        "million dollar", "us-550", "vail", "eisenhower", "loveland pass",
        "pch", "big sur", "coastal highway 1", "molas", "red mountain",
        "ouray", "durango", "silverton", "breckenridge", "telluride",
    ]
    rl = route.lower()
    return any(m in rl for m in markers)


def _is_long_rural_route(route: str, dur_min: float) -> bool:
    """True for long remote routes where gas stations and extended content matter."""
    rural_markers = [
        "us-50", "us 50", "loneliest road", "nevada", "ely", "fallon",
        "death valley", "mojave", "great basin", "us-93", "us-93",
    ]
    rl = route.lower()
    return dur_min >= 15 or any(m in rl for m in rural_markers)


# ---------- Hardcoded fallback path (no API key) ----------

async def _run_scripted(signal: dict, ctx: _Ctx) -> None:
    route_id    = signal["route_id"]
    deadzone_id = signal["deadzone_id"]
    user_id     = signal["user_id"]
    buyer_agent = "agent_" + user_id.split("_")[-1]
    dur_min     = signal.get("duration_minutes", 4)
    zone_desc   = signal.get("zone_description", "")
    route_label = signal.get("route", route_id.replace("_", " "))

    # Human-readable location hint for search queries — prefer zone description, else route name
    location = zone_desc if zone_desc else route_label

    # Step 1: cache lookup
    cache_result = await _timed_dispatch(
        "clickhouse_find_recent_pack",
        {"route_id": route_id, "deadzone_id": deadzone_id, "max_age_min": 10},
        ctx,
    )

    if cache_result.get("found"):
        cached_pack = cache_result["pack"]
        ctx.pack_id = cached_pack["pack_id"]  # set before payments_pay for log_payment
        seller_agent = "agent_" + cached_pack["owner_user_id"].split("_")[-1]

        await _timed_dispatch("payments_pay", {
            "from_agent": buyer_agent, "to_agent": seller_agent,
            "amount_usd": PRICE_USD, "memo": "buy cached pack",
        }, ctx)

        await _timed_dispatch("clickhouse_log_event", {
            "user_id": user_id, "route_id": route_id, "deadzone_id": deadzone_id,
            "action": "bought", "pack_id": cached_pack["pack_id"], "build_ms": 0,
        }, ctx)

        await _timed_dispatch("deliver_pack", {
            "url": cached_pack["url"], "cached": True, "pack_id": cached_pack["pack_id"],
        }, ctx)

        await _eval_pack(ctx)
        return

    # Step 2: parallel web searches — classify route type for targeted queries
    transit     = is_transit_route(route_label)
    mountain    = _is_mountain_route(route_label)
    long_rural  = _is_long_rural_route(route_label, dur_min)

    if transit:
        # Transit: service alerts and commuter-relevant info
        if dur_min >= 5:
            topics = [
                ("road",    f"transit service alerts delays {location} {route_label} today"),
                ("news",    f"local news commuter updates {location} {route_label}"),
                ("poi",     f"nearby services exits points of interest near {location}"),
                ("weather", f"weather forecast {location}"),
            ]
        elif dur_min >= 2:
            topics = [
                ("road",    f"transit service alerts delays {location} {route_label} today"),
                ("news",    f"commuter news updates {location} {route_label}"),
                ("weather", f"weather forecast {location}"),
            ]
        else:
            topics = [
                ("road", f"transit service alerts {location} {route_label}"),
                ("news", f"local news {location}"),
            ]
    elif mountain:
        # Mountain routes: safety is critical — always 4 searches including emergency contacts
        topics = [
            ("weather", f"high elevation mountain weather {location} {route_label} forecast storm alerts"),
            ("road",    f"road conditions closures rockslide avalanche {location} {route_label} CDOT"),
            ("poi",     f"emergency contacts search rescue county sheriff services near {location} {route_label}"),
            ("news",    f"local mountain news road closures weather {location} {route_label}"),
        ]
    elif long_rural:
        # Long rural routes (US-50, remote highways): scale content for extended blackout
        topics = [
            ("weather", f"weather forecast next 4 hours {location} {route_label}"),
            ("road",    f"road conditions open highways {location} {route_label} NDOT UDOT"),
            ("poi",     f"last gas station fuel services before {location} {route_label} emergency services"),
            ("news",    f"local news {location} {route_label}"),
        ]
    else:
        # Driving: weather, real-time road conditions, POI, local news
        if dur_min >= 5:
            topics = [
                ("weather", f"weather forecast {location} driving {route_label}"),
                ("road",    f"road conditions traffic construction alerts {location} {route_label}"),
                ("poi",     f"rest stops gas stations services near {location} {route_label}"),
                ("news",    f"local news traffic incidents {location} {route_label}"),
            ]
        elif dur_min >= 2:
            topics = [
                ("weather", f"weather forecast {location} {route_label}"),
                ("road",    f"road conditions traffic alerts {location} {route_label}"),
                ("news",    f"local news {location} {route_label}"),
            ]
        else:
            topics = [
                ("road", f"road conditions traffic {location} {route_label}"),
                ("news", f"local news {location} {route_label}"),
            ]

    search_results = await asyncio.gather(*[
        _timed_dispatch("nimble_search", {"query": q, "topic": t}, ctx)
        for t, q in topics
    ])

    _HEADINGS_DRIVING = {
        "weather": "Weather",
        "road":    "Road conditions",
        "poi":     "Nearby services",
        "news":    "Local news",
    }
    _HEADINGS_TRANSIT = {
        "weather": "Weather",
        "road":    "Transit alerts & delays",
        "poi":     "Nearby services & exits",
        "news":    "Local news",
    }
    _HEADINGS_MOUNTAIN = {
        "weather": "Mountain weather & alerts",
        "road":    "Road conditions & closures",
        "poi":     "Emergency contacts & services",
        "news":    "Local & road news",
    }
    _HEADINGS_RURAL = {
        "weather": "Weather forecast",
        "road":    "Road conditions & fuel",
        "poi":     "Services before the dead zone",
        "news":    "Local news",
    }
    if transit:
        _HEADINGS = _HEADINGS_TRANSIT
    elif mountain:
        _HEADINGS = _HEADINGS_MOUNTAIN
    elif long_rural:
        _HEADINGS = _HEADINGS_RURAL
    else:
        _HEADINGS = _HEADINGS_DRIVING
    sections = [{
        "heading": _HEADINGS.get(t, t.title()),
        "summary": r.get("summary", ""),
        "sources": r.get("sources", []),
    } for (t, _), r in zip(topics, search_results)]

    # Step 3: publish
    title = f"Offline pack: {zone_desc or route_id}"
    pub_result = await _timed_dispatch("senso_publish", {
        "title": title, "route_id": route_id, "sections": sections,
    }, ctx)

    if "error" in pub_result:
        err_ev = {
            "type": "log", "level": "error",
            "msg": "senso publish failed; aborting",
            "trace_id": ctx.trace_id, "t_ms": _now_ms(ctx),
        }
        await emit(err_ev)
        db.append_trace_event(ctx.trace_id, err_ev)
        await _eval_pack(ctx)
        return

    url = pub_result.get("url", "")
    source_count = sum(len(s.get("sources", [])) for s in sections)

    # Step 4: persist
    await _timed_dispatch("clickhouse_save_pack", {
        "route_id": route_id, "deadzone_id": deadzone_id, "url": url,
        "owner_user_id": user_id, "source_count": source_count,
    }, ctx)

    # Step 5: telemetry
    await _timed_dispatch("clickhouse_log_event", {
        "user_id": user_id, "route_id": route_id, "deadzone_id": deadzone_id,
        "action": "built", "pack_id": ctx.pack_id, "build_ms": _now_ms(ctx),
    }, ctx)

    # Step 6: deliver
    await _timed_dispatch("deliver_pack", {
        "url": url, "cached": False, "pack_id": ctx.pack_id,
    }, ctx)

    # Emit a human-readable delivery confirmation using actual signal data
    deliver_label = zone_desc or route_label
    deliver_ev = {
        "type": "log", "level": "info",
        "msg":  f"Delivering fresh offline pack for {deliver_label}",
        "trace_id": ctx.trace_id, "t_ms": _now_ms(ctx),
    }
    await emit(deliver_ev)
    db.append_trace_event(ctx.trace_id, deliver_ev)

    await _eval_pack(ctx)
