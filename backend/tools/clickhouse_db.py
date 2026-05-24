"""ClickHouse wrapper with in-memory fallback so the demo runs without setup."""
from __future__ import annotations
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

_USE_CH = bool(os.getenv("CLICKHOUSE_HOST"))
_client = None

# In-memory tables â€” same shape as ClickHouse rows.
# Capped to avoid unbounded memory growth in demo/dev mode.
_MAX_ROWS = 1000
_packs: list[dict] = []
_events: list[dict] = []
_payments: list[dict] = []
_signal_history: list[dict] = []


def _get_client():
    global _client, _USE_CH
    if _client is not None:
        return _client
    import clickhouse_connect
    try:
        _client = clickhouse_connect.get_client(
            host=os.environ["CLICKHOUSE_HOST"],
            username=os.getenv("CLICKHOUSE_USER", "default"),
            password=os.getenv("CLICKHOUSE_PASSWORD", ""),
            secure=True,
        )
        return _client
    except Exception as e:
        print(f"[clickhouse_db] Connection failed: {e} â€” falling back to in-memory store.")
        _USE_CH = False
        return None


def init_db() -> None:
    """Create tables if using real ClickHouse. No-op for in-memory."""
    if not _USE_CH:
        print("[clickhouse_db] CLICKHOUSE_HOST not set â€” using in-memory store.")
        return
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "schema.sql")) as f:
        ddl = f.read()
    cli = _get_client()
    if cli is None:
        return  # fell back to in-memory during connection attempt
    for stmt in [s.strip() for s in ddl.split(";") if s.strip()]:
        cli.command(stmt)
    print("[clickhouse_db] schema applied.")


def find_recent_pack(route_id: str, deadzone_id: str, max_age_min: int = 10) -> Optional[dict]:
    cutoff = datetime.utcnow() - timedelta(minutes=max_age_min)
    if not _USE_CH:
        candidates = [
            p for p in _packs
            if p["route_id"] == route_id
            and p["deadzone_id"] == deadzone_id
            and p["created_at"] >= cutoff
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p["created_at"])
    cli = _get_client()
    rows = cli.query(
        "SELECT pack_id, route_id, deadzone_id, url, owner_user_id, created_at, source_count "
        "FROM packs WHERE route_id=%(r)s AND deadzone_id=%(d)s AND created_at >= %(c)s "
        "ORDER BY created_at DESC LIMIT 1",
        parameters={"r": route_id, "d": deadzone_id, "c": cutoff},
    ).result_rows
    if not rows:
        return None
    r = rows[0]
    return {
        "pack_id": r[0], "route_id": r[1], "deadzone_id": r[2], "url": r[3],
        "owner_user_id": r[4], "created_at": r[5], "source_count": r[6],
    }


def save_pack(route_id: str, deadzone_id: str, url: str, owner_user_id: str,
              source_count: int, created_at: Optional[datetime] = None) -> str:
    pack_id = "pk_" + uuid.uuid4().hex[:10]
    row = {
        "pack_id": pack_id, "route_id": route_id, "deadzone_id": deadzone_id,
        "url": url, "owner_user_id": owner_user_id,
        "created_at": created_at or datetime.utcnow(), "source_count": source_count,
    }
    if not _USE_CH:
        _packs.append(row)
        if len(_packs) > _MAX_ROWS:
            del _packs[: len(_packs) - _MAX_ROWS]
        return pack_id
    cli = _get_client()
    cli.insert("packs", [[
        row["pack_id"], row["route_id"], row["deadzone_id"], row["url"],
        row["owner_user_id"], row["created_at"], row["source_count"],
    ]], column_names=[
        "pack_id", "route_id", "deadzone_id", "url",
        "owner_user_id", "created_at", "source_count",
    ])
    return pack_id


def log_event(user_id: str, route_id: str, deadzone_id: str, action: str,
              pack_id: str = "", build_ms: int = 0) -> None:
    row = {
        "event_id": "ev_" + uuid.uuid4().hex[:10],
        "user_id": user_id, "route_id": route_id, "deadzone_id": deadzone_id,
        "action": action, "pack_id": pack_id, "build_ms": build_ms,
        "ts": datetime.utcnow(),
    }
    if not _USE_CH:
        _events.append(row)
        if len(_events) > _MAX_ROWS:
            del _events[: len(_events) - _MAX_ROWS]
        return
    cli = _get_client()
    cli.insert("events", [[
        row["event_id"], row["user_id"], row["route_id"], row["deadzone_id"],
        row["action"], row["pack_id"], row["build_ms"], row["ts"],
    ]], column_names=[
        "event_id", "user_id", "route_id", "deadzone_id",
        "action", "pack_id", "build_ms", "ts",
    ])


def log_payment(tx_id: str, from_user: str, to_user: str, amount_usd: float, pack_id: str) -> None:
    row = {
        "tx_id": tx_id, "from_user": from_user, "to_user": to_user,
        "amount_usd": amount_usd, "pack_id": pack_id,
        "ts": datetime.utcnow(),
    }
    if not _USE_CH:
        _payments.append(row)
        if len(_payments) > _MAX_ROWS:
            del _payments[: len(_payments) - _MAX_ROWS]
        return
    cli = _get_client()
    cli.insert("payments", [[
        row["tx_id"], row["from_user"], row["to_user"],
        row["amount_usd"], row["pack_id"], row["ts"],
    ]], column_names=[
        "tx_id", "from_user", "to_user", "amount_usd", "pack_id", "ts",
    ])


def dashboard_summary() -> dict[str, Any]:
    day_ago = datetime.utcnow() - timedelta(hours=24)
    if not _USE_CH:
        built = sum(1 for e in _events if e["action"] == "built")
        bought = sum(1 for e in _events if e["action"] == "bought")
        paid = sum(p["amount_usd"] for p in _payments)
        recent_build_ms = [e["build_ms"] for e in _events
                           if e["action"] == "built" and e["ts"] >= day_ago and e["build_ms"] > 0]
        avg_ms = int(sum(recent_build_ms) / len(recent_build_ms)) if recent_build_ms else 0
        recent = sorted(_events, key=lambda e: e["ts"], reverse=True)[:5]
        recent_serial = [{
            "user_id": e["user_id"], "action": e["action"],
            "deadzone_id": e["deadzone_id"], "pack_id": e["pack_id"],
            "ts": e["ts"].isoformat(),
        } for e in recent]
        recent_packs = sorted(_packs, key=lambda p: p["created_at"], reverse=True)[:5]
        recent_packs_serial = [{
            "pack_id": p["pack_id"], "url": p["url"],
            "route_id": p["route_id"], "deadzone_id": p["deadzone_id"],
            "owner_user_id": p["owner_user_id"],
            "created_at": p["created_at"].isoformat(),
        } for p in recent_packs]
        return {
            "packs_built": built, "packs_sold": bought,
            "total_paid_usd": round(paid, 4), "avg_build_ms": avg_ms,
            "recent_events": recent_serial, "recent_packs": recent_packs_serial,
        }
    cli = _get_client()
    built = cli.query("SELECT count() FROM events WHERE action='built'").result_rows[0][0]
    bought = cli.query("SELECT count() FROM events WHERE action='bought'").result_rows[0][0]
    paid = cli.query("SELECT sum(amount_usd) FROM payments").result_rows[0][0] or 0.0
    avg_ms_row = cli.query(
        "SELECT avg(build_ms) FROM events WHERE action='built' AND build_ms > 0 AND ts >= %(c)s",
        parameters={"c": day_ago},
    ).result_rows[0][0] or 0
    recent = cli.query(
        "SELECT user_id, action, deadzone_id, pack_id, ts FROM events ORDER BY ts DESC LIMIT 5"
    ).result_rows
    recent_packs = cli.query(
        "SELECT pack_id, url, route_id, deadzone_id, owner_user_id, created_at "
        "FROM packs ORDER BY created_at DESC LIMIT 5"
    ).result_rows
    return {
        "packs_built": int(built), "packs_sold": int(bought),
        "total_paid_usd": round(float(paid), 4), "avg_build_ms": int(avg_ms_row),
        "recent_events": [{
            "user_id": r[0], "action": r[1], "deadzone_id": r[2],
            "pack_id": r[3], "ts": r[4].isoformat(),
        } for r in recent],
        "recent_packs": [{
            "pack_id": r[0], "url": r[1], "route_id": r[2],
            "deadzone_id": r[3], "owner_user_id": r[4],
            "created_at": r[5].isoformat(),
        } for r in recent_packs],
    }


def has_any_events() -> bool:
    if not _USE_CH:
        return len(_events) > 0
    cli = _get_client()
    return cli.query("SELECT count() FROM events").result_rows[0][0] > 0


def save_signal_quality(route_id: str, lat: float, lng: float,
                        signal_dbm: int, timestamp: Optional[datetime] = None) -> None:
    """Record a signal quality observation for a route segment."""
    row = {
        "route_id": route_id,
        "lat": lat,
        "lng": lng,
        "signal_dbm": signal_dbm,
        "ts": timestamp or datetime.utcnow(),
    }
    _signal_history.append(row)
    if len(_signal_history) > _MAX_ROWS:
        del _signal_history[: len(_signal_history) - _MAX_ROWS]


def get_signal_history(route_id: str) -> list[dict]:
    """Return all signal quality records for a given route_id."""
    return [r for r in _signal_history if r["route_id"] == route_id]


# ── Trace / replay storage ────────────────────────────────────────────────────

_traces: dict[str, list] = {}
_MAX_TRACES = 50


def append_trace_event(trace_id: str, event: dict) -> None:
    """Record one event against a trace for later replay."""
    if trace_id not in _traces:
        if len(_traces) >= _MAX_TRACES:
            # Evict the oldest trace (dict preserves insertion order in Python 3.7+)
            oldest = next(iter(_traces))
            del _traces[oldest]
        _traces[trace_id] = []
    _traces[trace_id].append(event)


def get_trace(trace_id: str) -> list[dict]:
    """Return all recorded events for a trace (empty list if unknown)."""
    return list(_traces.get(trace_id, []))


def list_traces() -> list[str]:
    """Return trace IDs ordered most-recent-first."""
    return list(reversed(list(_traces.keys())))
