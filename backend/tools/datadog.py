"""Datadog LLM Observability initialization.

Call `init()` ONCE at process startup BEFORE any code uses the OpenAI SDK. After init,
- the OpenAI SDK is auto-instrumented (every chat.completions.create becomes an LLM span)
- the @workflow / @agent / @tool decorators in ddtrace.llmobs.decorators emit spans
- everything streams to Datadog LLM Observability (no Agent process needed —
  agentless_enabled=True sends directly to the intake API)

If DD_API_KEY is unset, init() is a no-op. The decorators are still safe to use
(they simply don't emit anywhere).

Docs: https://docs.datadoghq.com/llm_observability/
"""
from __future__ import annotations
import os

_API_KEY = os.getenv("DD_API_KEY", "").strip() or os.getenv("DATADOG_API_KEY", "").strip()
_SITE = (os.getenv("DD_SITE", "") or os.getenv("DATADOG_SITE", "datadoghq.com")).strip()
_ML_APP = os.getenv("DD_LLMOBS_ML_APP", "deadzone-agent").strip()

_enabled = False


def enabled() -> bool:
    return _enabled


def init() -> None:
    """Enable LLM Observability. Safe to call multiple times; no-op without DD_API_KEY."""
    global _enabled
    if _enabled:
        return
    if not _API_KEY:
        print("[datadog] DD_API_KEY not set — LLM Observability disabled "
              "(decorators will no-op).")
        # LLMObs.annotate() throws when called without an active span even when
        # disabled, so patch it to a true no-op so every call site is safe.
        try:
            from ddtrace.llmobs import LLMObs
            LLMObs.annotate = staticmethod(lambda *a, **kw: None)
        except Exception:
            pass
        return
    try:
        from ddtrace.llmobs import LLMObs
        LLMObs.enable(
            ml_app=_ML_APP,
            api_key=_API_KEY,
            site=_SITE,
            agentless_enabled=True,
        )
        _enabled = True
        print(f"[datadog] LLM Observability enabled — ml_app={_ML_APP!r} site={_SITE!r}")
    except Exception as e:
        print(f"[datadog] LLM Observability init failed: {e}")
