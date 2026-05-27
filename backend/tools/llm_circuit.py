"""Shared LLM circuit breaker for the whole agentic stack.

Why this exists
---------------
Agents (agent1.predict, orchestrator._run_with_llm, nimble._llm_stub) all call
the same OpenRouter → Groq provider chain. When that chain is unhealthy
(provider 402, 429, 5xx, timeout), every component pays a 30s+ timeout PER
REQUEST trying to discover the same dead provider. During a LinkedIn-launch
traffic spike that compounds badly.

Solution: one process-level breaker shared by all callers. The first
component that observes a full provider-chain failure trips it; everyone else
short-circuits to their fail-safe path until the cooldown elapses. The first
successful LLM call after cooldown closes it again.

This keeps the system AGENTIC by default — the LLM is always the primary
path. The breaker only activates after an observed failure, and resets
automatically.

Usage
-----
    from tools.llm_circuit import is_open, trip, reset, status

    if is_open():
        return fallback()              # skip the LLM, go straight to safety
    try:
        result = await call_llm(...)
        reset()                        # provider recovered
        return result
    except Exception as e:
        trip(f"{type(e).__name__}")    # tell everyone else the LLM is down
        return fallback()
"""
from __future__ import annotations
import os
import time

# Module-level state. Process-local — Railway runs a single worker so this is
# fine for the demo. For multi-worker deploys, swap for Redis-backed state.
_open_until: float = 0.0
_cooldown  : float = float(os.getenv("LLM_CIRCUIT_COOLDOWN_SEC", "300"))  # 5 min default
_last_reason: str = ""
_trip_count : int = 0


def is_open() -> bool:
    """True if the breaker is currently tripped (skip the LLM)."""
    return time.time() < _open_until


def trip(reason: str = "") -> None:
    """Trip the breaker for `cooldown_seconds`. Idempotent — re-tripping extends the window."""
    global _open_until, _last_reason, _trip_count
    _open_until = time.time() + _cooldown
    _last_reason = reason or "unknown"
    _trip_count += 1
    print(f"[llm_circuit] OPEN for {int(_cooldown)}s (reason: {_last_reason}, trips: {_trip_count})", flush=True)


def reset() -> None:
    """Close the breaker (call after a successful LLM round-trip)."""
    global _open_until
    if _open_until > 0:
        print("[llm_circuit] CLOSED (provider recovered)", flush=True)
    _open_until = 0.0


def status() -> dict:
    """Diagnostic snapshot for /llm-check."""
    now = time.time()
    return {
        "open":              now < _open_until,
        "seconds_remaining": max(0, int(_open_until - now)),
        "cooldown_seconds":  int(_cooldown),
        "last_reason":       _last_reason,
        "trip_count":        _trip_count,
    }


def seconds_remaining() -> int:
    return max(0, int(_open_until - time.time()))
