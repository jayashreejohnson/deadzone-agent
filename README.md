# DeadZone Agent

> An AI agent that builds you a cited offline content pack right before you lose signal — and sells it to the next driver who hits the same dead zone.

## The problem

You're driving NYC → Burlington. Twenty miles of the Adirondacks have no cell service. By the time the bars drop you've lost the weather, the road conditions, the news, the "is that gas station still open" question — all of it. You only notice once it's already too late.

## What DeadZone Agent does

When your car is ~4 minutes out from a known dead zone, the agent wakes up and **autonomously**:

```
detect dead zone  →  LLM reasons about what you'll need
       ↓
       searches the web (weather · roads · POIs · local news)
       ↓
       publishes a cited, offline-readable pack to a public URL
       ↓
       delivers it to your phone before you lose signal
```

You see a banner go ⚠️ → 🔄 → ✅ and a live log of every tool call the agent makes. Tap the banner, get the pack.

## How the agent works (the interesting part)

The orchestrator is **not a hardcoded pipeline.** It's an OpenAI function-calling loop — the LLM is given a set of tools as JSON schemas and decides which to call, in what order, with what arguments.

Tools the agent has:

- `nimble_search(query)` — web search via Nimble
- `senso_publish(title, sections)` — publish a cited pack to `cited.md`
- `clickhouse_find_recent_pack(route_id, deadzone_id)` — cache lookup
- `clickhouse_save_pack(...)` / `clickhouse_log_event(...)` — telemetry
- `payments_pay(from, to, amount)` — agent-to-agent settlement

Loop pattern (per [OpenAI's function-calling guide](https://developers.openai.com/api/docs/guides/function-calling)):

1. Send messages + tool schemas to the model.
2. If the response includes `tool_calls`, run them and append results as `role: "tool"` messages.
3. Repeat until the model returns plain text. Done.

Every tool wrapper emits a WebSocket event when invoked, so the UI streams the agent's reasoning live. That's the "visible autonomy" you see in the log panel.

## Agent-to-agent payments

When **user B** drives the same route and hits the same dead zone, their agent finds the pack **user A's agent** already built — and *buys it* instead of rebuilding it.

- Real Coinbase CDP wallet on Base Sepolia testnet (you'll see the address on screen).
- Simulated x402 settlement (fake tx hash) so the demo never blocks on faucets.
- The dashboard ticks up: `1 sold · $0.02 paid`.

This is the pitch: agents transacting with each other for already-done work, with the LLM deciding when to buy vs. when to build.

## Tech stack

- **Backend:** Python 3.11 · FastAPI · OpenAI SDK (function calling) · `clickhouse-connect` · `httpx` · WebSockets
- **Frontend:** Next.js 14 (App Router) · TypeScript · Tailwind · `react-leaflet`
- **Storage:** ClickHouse Cloud (free tier)
- **Sponsors:** Nimble (web search) · Senso (publish to cited.md) · Coinbase CDP + x402 (payments)

## Repo layout

```
deadzone/
├── backend/
│   ├── main.py                    # FastAPI app + OpenAI tool-calling loop + /ws
│   ├── tools/
│   │   ├── nimble.py              # web search (with stub fallback)
│   │   ├── senso.py               # publish to cited.md (with static-file fallback)
│   │   ├── clickhouse_db.py       # cache + telemetry
│   │   └── payments.py            # CDP wallet + simulated x402 transfer
│   ├── schema.sql                 # ClickHouse DDL
│   ├── seed.py                    # pre-seed packs/events so the dashboard isn't empty
│   └── requirements.txt
└── frontend/
    ├── app/page.tsx               # the only page — map + log panel + dashboard
    ├── lib/route.ts               # hardcoded NYC→Burlington polyline + dead zones
    └── components/                # Banner, Map, PackModal, Dashboard
```

## Quick start

```bash
# 1. Backend
cd backend
cp .env.example .env       # fill in OPENAI_API_KEY, NIMBLE_API_KEY, SENSO_API_KEY,
                           # CLICKHOUSE_*, CDP_API_KEY, CDP_API_SECRET
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 2. Frontend (new terminal)
cd frontend
npm install
npm run dev

# 3. Open http://localhost:3000
```

Missing API keys? Every tool wrapper has a deterministic stub fallback so the demo still runs end-to-end.

## Demo flow

1. **User A starts a trip.** Dot moves along the route. Hits the first dead zone. Banner ⚠️ → 🔄. Log panel streams the agent's tool calls (Nimble × N, Senso publish, ClickHouse writes). Banner ✅. Tap it → modal opens with the live `cited.md` page.
2. **Switch to User B. Start their trip.** Same route, same dead zone. This time the agent finds the cached pack, fires a payment to User A, and delivers in ~1 second. Banner shows a "bought from agent_a — $0.02" badge.
3. **Bottom dashboard:** `1 built · 1 sold · $0.02 paid · ~8s avg build`.

That's the demo. If those three steps work, the submission works.

## Status

Hackathon project. No tests, no auth, no Docker, no production hardening. The point is to show an LLM-driven agent loop that uses real sponsor APIs, falls back gracefully, and demonstrates a believable agent-to-agent economy in under three minutes.
