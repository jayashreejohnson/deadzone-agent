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

# Short per-request timeout so a dead/queued provider doesn't drag.
# 5s is aggressive enough to catch queued Cerebras free-tier calls while
# being generous for healthy Gemini/Llama (typically 1-3s).
_LLM_TIMEOUT_SEC  = float(os.getenv("LLM_TIMEOUT_SEC", "5"))

# ORCHESTRATOR_MODE controls whether we use the LLM tool-calling loop or the
# deterministic scripted flow.
#   "agentic"  -> LLM picks tools. THE DEFAULT. This IS the project — the
#                 agentic loop is what makes DeadZone DeadZone, not a glorified
#                 cron job. Scripted is ONLY a real failsafe (used when every
#                 provider's breaker is open AFTER an observed failure).
#   "scripted" -> hardcoded tool sequence (10-15s, deterministic, no LLM hops).
#                 Opt-in only.
#   "auto"     -> agentic, but pre-emptively skip to scripted if OpenRouter
#                 is unhealthy. NOT default — opt-in for situations where you
#                 explicitly want speed over agentic behavior.
_ORCHESTRATOR_MODE = os.getenv("ORCHESTRATOR_MODE", "agentic").strip().lower()

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
        # Defensive coercion: free-tier LLMs sometimes pass strings or
        # malformed entries inside `sections`. Senso's HTML renderer expects
        # a list of dicts with heading/summary/sources keys — coerce here so
        # the LLM doesn't have to waste another round-trip recovering.
        title    = args.get("title") or f"Offline pack: {ctx.signal.get('zone_description', 'route')}"
        route_id = args.get("route_id") or ctx.signal.get("route_id", "")
        raw_secs = args.get("sections") or []
        if not isinstance(raw_secs, list):
            raw_secs = [raw_secs]
        clean_secs: list[dict] = []
        for s in raw_secs:
            if isinstance(s, dict):
                clean_secs.append({
                    "heading": str(s.get("heading") or s.get("title") or "Section"),
                    "summary": str(s.get("summary") or s.get("content") or s.get("text") or ""),
                    "sources": s.get("sources") if isinstance(s.get("sources"), list) else [],
                })
            elif isinstance(s, str):
                # LLM passed a bare string — wrap it as a single section.
                clean_secs.append({"heading": "Notes", "summary": s, "sources": []})
        url = await senso.publish(title, route_id, clean_secs)
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

    # Decide between the LLM tool loop and the scripted flow.
    #
    # The LLM tool loop is more adaptive but each iteration costs one LLM
    # round-trip. When the only available providers are slow (Cerebras
    # free-tier queue) or unreliable (Groq 429s), a single pack can take
    # 60-400+ seconds — past the user's 4-minute countdown. The scripted
    # flow does the same parallel nimble searches and senso publish in
    # ~10-15s without any LLM hops.
    use_agentic = _OPENAI_KEY and not llm_circuit.is_open()
    if _ORCHESTRATOR_MODE == "scripted":
        use_agentic = False
    elif _ORCHESTRATOR_MODE == "agentic":
        # Forced agentic — honor it even if breaker is open (the user explicitly opted in).
        use_agentic = bool(_OPENAI_KEY)
    elif _ORCHESTRATOR_MODE == "auto":
        # Auto: use agentic only if OpenRouter (the strongest tool-caller in
        # our chain) is currently healthy. Otherwise the free-tier fallbacks
        # are too slow/sloppy for the tool loop; go scripted to hit the SLA.
        openrouter_alive = bool(_OPENROUTER_KEY) and not llm_circuit.is_open("openrouter")
        use_agentic = openrouter_alive

    if use_agentic:
        try:
            await _run_with_llm(signal, ctx)
            return
        except Exception as e:
            # Per-provider tripping already happened inside
            # _call_llm_with_fallback. Fall through to scripted.
            warn_ev = {
                "type": "log", "level": "warn",
                "msg":  f"LLM orchestrator failed ({e!s}); falling back to scripted flow",
                "trace_id": ctx.trace_id, "t_ms": _now_ms(ctx),
            }
            await emit(warn_ev)
            db.append_trace_event(ctx.trace_id, warn_ev)
    else:
        reason = (
            "ORCHESTRATOR_MODE=scripted"             if _ORCHESTRATOR_MODE == "scripted" else
            "OpenRouter unhealthy; free-tier LLMs too slow for tool loop" if _ORCHESTRATOR_MODE == "auto" else
            "all LLM providers' breakers open"
        )
        skip_ev = {
            "type": "log", "level": "info",
            "msg":  f"Using scripted flow ({reason})",
            "trace_id": ctx.trace_id, "t_ms": _now_ms(ctx),
        }
        await emit(skip_ev)
        db.append_trace_event(ctx.trace_id, skip_ev)
    await _run_scripted(signal, ctx)


# ---------- LLM-driven path ----------

# Base system prompt — common to every provider.
_PROMPT_CORE = """You build offline content packs for drivers about to lose cell signal. Speed matters.

INPUTS in signal: route, zone_description, duration_minutes, severity, lat, lng, user_id, route_id, deadzone_id.

THE ONE RULE: every run MUST end with deliver_pack. Without it the pack is lost.

ROUTE TYPE: transit (train/subway/BART/metro) | mountain (pass/Vail/Big Sur/Million Dollar/PCH/US-550) | rural (US-50/Nevada/loneliest/duration>=15) | tunnel (tunnel/Lincoln/Holland) | default.

STEP 1 — IN ONE PARALLEL BATCH, call clickhouse_find_recent_pack AND 2-4 nimble_search.
Queries (use zone_description and route in each):
  transit:  road="<zone> <route> service alerts delays", news="commuter news <zone>", poi="nearby exits <zone>", weather="weather <zone>"
  mountain: weather="mountain weather <zone> forecast", road="road conditions closures <zone>", poi="emergency contacts sheriff <zone>", news="local mountain news <zone>"
  rural:    weather="weather next 4h <zone>", road="road conditions gas stations <zone>", poi="last gas station <zone>", news="local news <zone>"
  tunnel:   road="traffic <zone> <route>", news="local news <zone>", weather="weather <route>", poi="rest stops <zone>"
Counts: duration>=5 → 4 topics; duration 2-4 → weather+road+news; duration<2 → road+news.

STEP 2 — Cache HIT: in parallel call payments_pay (from=agent_<last char of user_id>, to=agent_<last char of cached.owner_user_id>, amount_usd=0.02, memo="buy cached pack") AND clickhouse_log_event (action="bought", pack_id=cached.pack_id, build_ms=0) AND deliver_pack (url=cached.url, cached=true, pack_id=cached.pack_id). STOP.

STEP 3 — Cache MISS path: call senso_publish.
senso_publish args (EXACT shape, no exceptions):
  title: "Offline pack: <zone_description>"
  route_id: signal.route_id
  sections: [
    {"heading": "Weather", "summary": "<2-3 sentences from the weather search>", "sources": [{"url":"...","title":"...","snippet":"..."}]},
    {"heading": "Road conditions", "summary": "<...>", "sources": [...]},
    ...one object per topic returned...
  ]
Each section is an OBJECT. Never a string. Never markdown.

STEP 4 — Call clickhouse_save_pack(route_id, deadzone_id, url=<published url>, owner_user_id=signal.user_id, source_count=<total sources across sections>).

STEP 5 — MANDATORY: call deliver_pack(url=<published url>, cached=false, pack_id=<pack_id from save_pack>).

Parallel calls are cheap. Sequential calls cost a full round-trip — minimize them. No commentary between tool calls."""


# Per-provider system prompt variants. Different models have different
# strengths and quirks; tailor the wrapper around the shared core.
def _system_prompt_for(provider: str) -> str:
    if provider == "groq":
        # Llama 3.3 70B follows numbered imperatives well but can be sloppy
        # with required JSON fields. Drill the schema and the "must call
        # every step" rule extra hard.
        return (
            "You are a precise tool-calling agent. Follow every numbered step. "
            "Skipping a step means the user gets nothing — that's a critical failure. "
            "Always include every required argument. JSON shape matters.\n\n"
            + _PROMPT_CORE
        )
    if provider == "cerebras":
        # gpt-oss-120b / zai-glm-4.7 on Cerebras. Smaller prompts get faster
        # responses on their hardware. Strip the "you are" framing.
        return _PROMPT_CORE
    # OpenRouter / Gemini: handles natural language well, takes the core as-is.
    return _PROMPT_CORE


# Back-compat — some other module imports SYSTEM_PROMPT directly.
SYSTEM_PROMPT = _PROMPT_CORE


async def _call_llm_with_fallback(
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: object = "auto",
):
    """Try OpenRouter, then Groq, then Cerebras. Each provider gets its own
    system prompt (different models follow instructions differently) and
    its own per-call kwargs (parallel_tool_calls, max_tokens, etc.)."""
    from openai import AsyncOpenAI
    last_error: Exception | None = None

    def _msgs_for(provider: str) -> list[dict]:
        """Swap the system prompt for the provider-specific variant."""
        sys_prompt = _system_prompt_for(provider)
        out = list(messages)
        if out and out[0].get("role") == "system":
            out[0] = {"role": "system", "content": sys_prompt}
        else:
            out.insert(0, {"role": "system", "content": sys_prompt})
        return out

    def _tool_kwargs(provider: str) -> dict:
        if not tools:
            return {}
        # Cerebras's zai-glm-4.7 returns 400 ('Failed to generate tool_...')
        # when given a specific {type:function, function:{name:...}}
        # tool_choice — it doesn't reliably handle the forced-function
        # syntax. Downgrade to 'required' (model picks among the allowed
        # tools, which is fine because `tools` is already filtered to the
        # one we want). 'auto' is left alone.
        effective_choice = tool_choice
        if provider == "cerebras" and isinstance(tool_choice, dict):
            effective_choice = "required"

        kw: dict = {"tools": tools, "tool_choice": effective_choice}
        # Gemini (OpenRouter) and Llama (Groq) handle parallel tool calls
        # well. Cerebras gpt-oss / GLM-4 do not — passing the flag returns
        # 400, so we omit it there.
        if provider != "cerebras":
            kw["parallel_tool_calls"] = True
        return kw

    def _max_tokens_for(provider: str) -> int:
        # Smaller token budget on Cerebras's queued free tier so the
        # response comes back sooner. Groq and OpenRouter can afford more
        # headroom for richer pack summaries.
        return 1024 if provider == "cerebras" else 2048

    if _OPENROUTER_KEY and not llm_circuit.is_open("openrouter"):
        try:
            c = AsyncOpenAI(api_key=_OPENROUTER_KEY, base_url="https://openrouter.ai/api/v1", timeout=_LLM_TIMEOUT_SEC, max_retries=0)
            kwargs = {"model": _OPENROUTER_MODEL, "messages": _msgs_for("openrouter"),
                      "temperature": 0, "max_tokens": _max_tokens_for("openrouter"),
                      **_tool_kwargs("openrouter")}
            resp = await c.chat.completions.create(**kwargs)
            llm_circuit.reset("openrouter")
            return resp, "openrouter"
        except Exception as e:
            print(f"[orchestrator] OpenRouter call failed: {type(e).__name__}: {str(e)[:160]}; trying Groq", flush=True)
            llm_circuit.classify_and_trip("openrouter", e)
            last_error = e
    elif _OPENROUTER_KEY:
        print(f"[orchestrator] OpenRouter circuit open ({llm_circuit.seconds_remaining('openrouter')}s); skipping", flush=True)

    if _GROQ_KEY and not llm_circuit.is_open("groq"):
        try:
            c = AsyncOpenAI(api_key=_GROQ_KEY, base_url="https://api.groq.com/openai/v1", timeout=_LLM_TIMEOUT_SEC, max_retries=0)
            kwargs = {"model": _GROQ_MODEL, "messages": _msgs_for("groq"),
                      "temperature": 0, "max_tokens": _max_tokens_for("groq"),
                      **_tool_kwargs("groq")}
            resp = await c.chat.completions.create(**kwargs)
            llm_circuit.reset("groq")
            return resp, "groq"
        except Exception as e:
            print(f"[orchestrator] Groq call failed: {type(e).__name__}: {str(e)[:160]}; trying Cerebras", flush=True)
            llm_circuit.classify_and_trip("groq", e)
            last_error = e
    elif _GROQ_KEY:
        print(f"[orchestrator] Groq circuit open ({llm_circuit.seconds_remaining('groq')}s); skipping", flush=True)

    if _CEREBRAS_KEY and not llm_circuit.is_open("cerebras"):
        try:
            c = AsyncOpenAI(api_key=_CEREBRAS_KEY, base_url="https://api.cerebras.ai/v1", timeout=_LLM_TIMEOUT_SEC, max_retries=0)
            kwargs = {"model": _CEREBRAS_MODEL, "messages": _msgs_for("cerebras"),
                      "temperature": 0, "max_tokens": _max_tokens_for("cerebras"),
                      **_tool_kwargs("cerebras")}
            resp = await c.chat.completions.create(**kwargs)
            llm_circuit.reset("cerebras")
            return resp, "cerebras"
        except Exception as e:
            print(f"[orchestrator] Cerebras call failed: {type(e).__name__}: {str(e)[:160]}", flush=True)
            llm_circuit.classify_and_trip("cerebras", e)
            last_error = e
    elif _CEREBRAS_KEY:
        print(f"[orchestrator] Cerebras circuit open ({llm_circuit.seconds_remaining('cerebras')}s); skipping", flush=True)

    raise last_error or RuntimeError("All LLM providers unavailable (all breakers open)")


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

    # State-machine forcing — see commit history for design notes.
    # The loop is wrapped in a try/except so that a mid-flow LLM failure
    # (provider 400, all breakers open, etc.) doesn't dump us back to a
    # cold _run_scripted. Instead we finalize from whatever the LLM
    # already produced (search results in the messages stream), so the
    # LLM's actual contribution is preserved.
    llm_loop_failed = False
    try:
        for _iter in range(6):
            searched     = "nimble_search" in ctx.tools_called
            has_pack_url = bool(ctx.pack_url)
            has_pack_id  = bool(ctx.pack_id)
            delivered    = ctx.delivered

            def _only(name: str) -> tuple[list[dict], object]:
                return (
                    [t for t in TOOLS if t["function"]["name"] == name],
                    {"type": "function", "function": {"name": name}},
                )

            if has_pack_id and not delivered:
                call_tools, tool_choice = _only("deliver_pack")
            elif has_pack_url and not has_pack_id:
                call_tools, tool_choice = _only("clickhouse_save_pack")
            elif searched and not has_pack_url:
                call_tools, tool_choice = _only("senso_publish")
            else:
                call_tools, tool_choice = TOOLS, "auto"

            resp, _provider = await _call_llm_with_fallback(
                messages, tools=call_tools, tool_choice=tool_choice,
            )
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
    except Exception as e:
        llm_loop_failed = True
        warn_ev = {
            "type": "log", "level": "warn",
            "msg":  f"LLM loop failed mid-flow ({type(e).__name__}); completing pack from accumulated state",
            "trace_id": ctx.trace_id, "t_ms": _now_ms(ctx),
        }
        await emit(warn_ev)
        db.append_trace_event(ctx.trace_id, warn_ev)

    # Finalize: walk forward through any missing steps using the work the
    # LLM already did (search results in `messages`). This preserves the
    # LLM's content decisions instead of throwing them away and starting
    # over with the scripted flow.
    if not ctx.delivered:
        await _finalize_from_messages(signal, ctx, messages, llm_loop_failed)

    await _eval_pack(ctx)


# ---------- Mid-flow finalizer ----------

async def _finalize_from_messages(signal: dict, ctx: _Ctx, messages: list[dict], from_failure: bool) -> None:
    """Walk forward through any remaining pack-building steps using the
    nimble_search results the LLM already produced.

    This is what runs when the LLM has done the agentic part (decided
    queries, pulled results) but stalls or 400s on senso_publish / save /
    deliver. The model's content decisions are preserved; we just glue
    the rest together. Falls back to _run_scripted only if NOTHING
    useful is in the messages stream (e.g. LLM died immediately)."""
    # Extract any nimble_search results from the tool messages.
    search_results: list[dict] = []
    cached_hit: dict | None = None
    for m in messages:
        if m.get("role") != "tool":
            continue
        name = m.get("name")
        try:
            payload = json.loads(m.get("content") or "{}")
        except Exception:
            continue
        if name == "nimble_search":
            search_results.append({
                "topic":   payload.get("topic", "info"),
                "summary": payload.get("summary", ""),
                "sources": payload.get("sources", []) or [],
            })
        elif name == "clickhouse_find_recent_pack" and payload.get("found"):
            cached_hit = payload.get("pack") or {}

    # Cache hit path: short-circuit pay + log + deliver.
    if cached_hit and not ctx.delivered:
        from_label = "agent_" + signal["user_id"].split("_")[-1]
        to_label   = "agent_" + cached_hit.get("owner_user_id", "x").split("_")[-1]
        ctx.pack_id = cached_hit["pack_id"]
        await _timed_dispatch("payments_pay", {
            "from_agent": from_label, "to_agent": to_label,
            "amount_usd": PRICE_USD, "memo": "buy cached pack",
        }, ctx)
        await _timed_dispatch("clickhouse_log_event", {
            "user_id": signal["user_id"], "route_id": signal["route_id"],
            "deadzone_id": signal["deadzone_id"], "action": "bought",
            "pack_id": cached_hit["pack_id"], "build_ms": 0,
        }, ctx)
        await _timed_dispatch("deliver_pack", {
            "url": cached_hit["url"], "cached": True, "pack_id": cached_hit["pack_id"],
        }, ctx)
        return

    # No searches and no cache result: fall back to scripted completely.
    if not search_results and not ctx.pack_url:
        if from_failure:
            warn_ev = {
                "type": "log", "level": "warn",
                "msg":  "No LLM-produced search results to finalize; falling back to scripted flow",
                "trace_id": ctx.trace_id, "t_ms": _now_ms(ctx),
            }
            await emit(warn_ev)
            db.append_trace_event(ctx.trace_id, warn_ev)
        await _run_scripted(signal, ctx)
        return

    # Step: publish, if not yet published.
    if not ctx.pack_url and search_results:
        _HEADINGS = {
            "weather": "Weather", "road": "Road conditions",
            "news":    "Local news", "poi": "Nearby services",
        }
        sections = [{
            "heading": _HEADINGS.get(r["topic"], r["topic"].title()),
            "summary": r["summary"],
            "sources": r["sources"],
        } for r in search_results]
        zone_desc = signal.get("zone_description") or signal.get("route", "route")
        await _timed_dispatch("senso_publish", {
            "title":    f"Offline pack: {zone_desc}",
            "route_id": signal["route_id"],
            "sections": sections,
        }, ctx)

    # Step: save, if not yet saved.
    if ctx.pack_url and not ctx.pack_id:
        source_count = sum(len(r["sources"]) for r in search_results)
        await _timed_dispatch("clickhouse_save_pack", {
            "route_id":      signal["route_id"],
            "deadzone_id":   signal["deadzone_id"],
            "url":           ctx.pack_url,
            "owner_user_id": signal["user_id"],
            "source_count":  source_count,
        }, ctx)

    # Step: deliver, mandatory.
    if not ctx.delivered and ctx.pack_url:
        await _timed_dispatch("deliver_pack", {
            "url":     ctx.pack_url,
            "cached":  False,
            "pack_id": ctx.pack_id,
        }, ctx)


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
