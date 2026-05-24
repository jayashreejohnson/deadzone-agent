#!/usr/bin/env python3
"""Quick functional test: run the scripted orchestrator path and check trace storage."""
import asyncio, sys
sys.path.insert(0, "/home/shageenth/deadzone/backend")

async def test():
    from tools.orchestrator import run
    from tools.clickhouse_db import list_traces, get_trace

    signal = {
        "user_id": "user_a",
        "lat": 40.75,
        "lng": -74.0,
        "eta_seconds": 300,
        "route_id": "test_route",
        "deadzone_id": "test_zone_1",
        "duration_minutes": 4,
        "severity": "medium",
        "zone_description": "Test Tunnel",
        "route": "Test Route A to B",
    }

    print("Running orchestrator scripted path...")
    await run(signal)

    traces = list_traces()
    print(f"Traces stored: {len(traces)} - {traces}")

    if traces:
        events = get_trace(traces[0])
        types = [e["type"] for e in events]
        print(f"Event types in trace: {types}")
        assert "trace_started" in types, "missing trace_started"
        assert "tool_start" in types, "missing tool_start"
        assert "tool_end" in types, "missing tool_end"
        assert "pack_ready" in types, "missing pack_ready"
        assert "eval_complete" in types, "missing eval_complete"

        # Check waterfall data
        tool_ends = [e for e in events if e["type"] == "tool_end"]
        print(f"Tool calls with timing:")
        for te in tool_ends:
            print(f"  {te['tool']:35s} t={te['t_ms']:4d}ms  latency={te['latency_ms']:4d}ms")

        # Check eval
        eval_ev = next(e for e in events if e["type"] == "eval_complete")
        print(f"Eval: score={eval_ev['score']}  coverage={eval_ev['coverage']}  sla_pass={eval_ev['sla_pass']}")

        trace_id = traces[0]
        print(f"trace_id = {trace_id}")
        assert trace_id.startswith("tr_"), "trace_id format wrong"

        print("\nALL ASSERTIONS PASSED")
    else:
        print("ERROR: no traces stored!")

asyncio.run(test())
