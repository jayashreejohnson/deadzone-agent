"""WebSocket event bus. Tools import `emit` to broadcast progress to all UI clients.

Datadog observability is handled separately by ddtrace's @workflow/@agent/@tool
decorators + OpenAI auto-instrumentation — no fan-out needed here.
"""
from __future__ import annotations
from typing import Any
from fastapi import WebSocket

_clients: set[WebSocket] = set()


async def register(ws: WebSocket) -> None:
    await ws.accept()
    _clients.add(ws)


def unregister(ws: WebSocket) -> None:
    _clients.discard(ws)


async def emit(event: dict[str, Any]) -> None:
    dead: list[WebSocket] = []
    for ws in list(_clients):
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)
