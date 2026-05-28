"""Per-provider LLM circuit breaker shared across the agentic stack.

Why per-provider
----------------
The earlier version tripped a single global breaker only when the ENTIRE
provider chain failed in one call. That helps during a total outage but
does nothing for the common case: one provider is dead (e.g. OpenRouter
402 / out of credits) while the others work. Every request would still
try the dead provider first, burn the per-call timeout, and fall through.

This version tracks each provider independently:

    if llm_circuit.is_open("openrouter"):
        skip openrouter      # try next provider directly
    try:
        result = await call("openrouter", ...)
        llm_circuit.reset("openrouter")
        return result
    except Exception as e:
        llm_circuit.trip("openrouter", reason, cooldown=<optional>)
        ...

Terminal errors (402 insufficient credits, 401 invalid key) get a long
cooldown (`TERMINAL_COOLDOWN_SEC`, default 1h) because they don't
self-recover within a minute. Transient errors (429, 5xx, timeout) get
the standard short cooldown so we retry quickly when things recover.

Back-compat: `is_open()` with no argument returns True only if ALL
known providers are currently open — i.e. the whole chain would skip
the LLM. Useful for callers that want to go straight to a non-LLM
fallback when nothing is reachable.
"""
from __future__ import annotations
import os
import time

# Default cooldown for transient failures (429, 5xx, timeout).
_DEFAULT_COOLDOWN  : float = float(os.getenv("LLM_CIRCUIT_COOLDOWN_SEC", "60"))
# Cooldown for terminal failures (402 out of credits, 401 invalid key).
_TERMINAL_COOLDOWN : float = float(os.getenv("LLM_CIRCUIT_TERMINAL_COOLDOWN_SEC", "3600"))  # 1h
# Known providers (used by is_open() with no arg, and by status()).
_KNOWN_PROVIDERS = ("openrouter", "groq", "cerebras")

# Per-provider state: {provider_name: (open_until_ts, last_reason, trip_count)}
_state: dict[str, tuple[float, str, int]] = {}


def _entry(provider: str) -> tuple[float, str, int]:
    return _state.get(provider, (0.0, "", 0))


def is_open(provider: str | None = None) -> bool:
    """True if the named provider is currently tripped.

    If `provider` is None, returns True only when EVERY known provider is
    currently open (i.e. the whole chain would be skipped). Lets callers
    short-circuit straight to a non-LLM fallback when nothing is reachable.
    """
    now = time.time()
    if provider is None:
        return all(_entry(p)[0] > now for p in _KNOWN_PROVIDERS)
    return _entry(provider)[0] > now


def trip(provider: str, reason: str = "", cooldown: float | None = None) -> None:
    """Trip a specific provider. Optional custom cooldown (seconds).

    For terminal errors (402, 401), pass `cooldown=_TERMINAL_COOLDOWN` or
    use `classify_and_trip()` which inspects the exception text.
    """
    dur = cooldown if cooldown is not None else _DEFAULT_COOLDOWN
    open_until = time.time() + dur
    _, _, count = _entry(provider)
    _state[provider] = (open_until, reason or "unknown", count + 1)
    print(f"[llm_circuit] OPEN {provider} for {int(dur)}s (reason: {reason or 'unknown'}, trips: {count + 1})", flush=True)


def reset(provider: str | None = None) -> None:
    """Close a specific provider's breaker. If `provider` is None, close all."""
    if provider is None:
        if _state:
            print("[llm_circuit] CLOSED all providers", flush=True)
        _state.clear()
        return
    if provider in _state and _state[provider][0] > 0:
        print(f"[llm_circuit] CLOSED {provider} (provider recovered)", flush=True)
    _state.pop(provider, None)


def classify_and_trip(provider: str, error: BaseException) -> None:
    """Trip with the right cooldown based on the exception type/text.

    Terminal markers (402 insufficient credits, 401 invalid key) get the
    longer cooldown so we don't keep retrying a key that's permanently
    dead for the day. Everything else gets the default short cooldown.
    """
    text = f"{type(error).__name__}: {str(error)[:200]}"
    low  = text.lower()
    terminal = any(s in low for s in (
        "402",
        "insufficient credit", "insufficient_credit",
        "401",
        "invalid api key", "invalid_api_key",
        "unauthorized",
        "no credits", "no_credits",
        "billing",
    ))
    cooldown = _TERMINAL_COOLDOWN if terminal else _DEFAULT_COOLDOWN
    reason = ("terminal:" if terminal else "transient:") + type(error).__name__
    trip(provider, reason, cooldown=cooldown)


def seconds_remaining(provider: str) -> int:
    return max(0, int(_entry(provider)[0] - time.time()))


def status() -> dict:
    """Diagnostic snapshot for /llm-check. Reports per-provider state."""
    now = time.time()
    providers = {}
    for p in _KNOWN_PROVIDERS:
        open_until, reason, count = _entry(p)
        providers[p] = {
            "open":              now < open_until,
            "seconds_remaining": max(0, int(open_until - now)),
            "last_reason":       reason,
            "trip_count":        count,
        }
    return {
        "providers":              providers,
        "all_open":               all(providers[p]["open"] for p in _KNOWN_PROVIDERS),
        "default_cooldown_sec":   int(_DEFAULT_COOLDOWN),
        "terminal_cooldown_sec":  int(_TERMINAL_COOLDOWN),
    }
