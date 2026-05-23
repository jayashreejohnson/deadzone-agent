"""Simulated x402-style agent-to-agent payment.

We don't talk to any real chain. Each agent has a fake wallet address and the
"settlement" returns a deterministic-looking sim transaction hash. This keeps
the demo reliable while still showing the agent-to-agent value-exchange story.
"""
from __future__ import annotations
import uuid
from bus import emit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

# Demo agent wallet addresses (shown to judges in console + UI events).
_AGENT_WALLETS: dict[str, str] = {
    "agent_a": "0xsim_a_8F2D9C4B7E13",
    "agent_b": "0xsim_b_3A6E1F92D8B5",
}


def wallet_for(agent: str) -> str:
    return _AGENT_WALLETS.get(agent, agent)


@tool(name="x402_pay")
async def pay(from_agent: str, to_agent: str, amount_usd: float, memo: str = "") -> dict:
    """Simulated x402 settlement. Returns {tx_id, amount, from, to}."""
    tx_id = "0xsim_" + uuid.uuid4().hex[:16]
    print(f"[payments] x402 (sim): {from_agent} → {to_agent}  "
          f"${amount_usd:.4f}  tx={tx_id}  memo={memo!r}")
    await emit({
        "type": "payment",
        "amount": amount_usd,
        "from": from_agent,
        "to": to_agent,
        "tx": tx_id,
    })
    result = {"tx_id": tx_id, "amount": amount_usd, "from": from_agent, "to": to_agent}
    LLMObs.annotate(
        input_data={"from": from_agent, "to": to_agent, "amount_usd": amount_usd, "memo": memo},
        output_data=result,
        metadata={"settlement": "x402_simulated", "from_wallet": wallet_for(from_agent),
                  "to_wallet": wallet_for(to_agent)},
        tags={"tool": "x402_pay"},
    )
    return result
