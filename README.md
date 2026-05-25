# DeadZone

> An AI agent that builds you a cited offline content pack right before you lose signal — and sells it to the next person who hits the same dead zone.

---

## The problem

You're driving through the Million Dollar Highway. Or riding the BART from Embarcadero to SFO. Or taking the L train under the East River. Every time, the same thing happens: by the time the bars drop you've already lost the weather, the road conditions, the news, the directions — all of it. You only notice once it's too late.

DeadZone fixes that. It detects the dead zone before you reach it, builds a complete cited offline pack, and delivers it to every screen you have — all before you lose signal.

---

## What it does

When a user is ~4 minutes from a known dead zone, the agent wakes up and:

```
detect dead zone  →  LLM reasons about what you'll need
       ↓
       searches the web (weather · roads · POIs · local news)
       ↓
       publishes a cited, offline-readable pack to a public URL
       ↓
       delivers it to your device before you lose signal
```

The UI shows a banner transition: ⚠️ → 🔄 → ✅. A live log panel streams every tool call the agent makes. Tap the banner to open the pack.

---

## Routes

DeadZone ships with **6 pre-built routes** — 3 driving, 3 transit — selectable from the trip planner:

**Driving**
- Manhattan → Newark (Lincoln Tunnel dead zone, ~4 min)
- Ouray → Durango via US-550 / Million Dollar Highway (Red Mountain Pass, alpine, ~25 min)
- Reno → Ely via US-50 / Loneliest Road in America (~80 min Nevada desert)

**Transit**
- NYC E train (Queens to Manhattan underground segment)
- NYC L train (Canarsie to 8th Ave under East River)
- BART Embarcadero → SFO (undersea Transbay tube)

Each route type drives a different content strategy. See [How the agent works](#how-the-agent-works) below.

---

## Demo flow

### Step 1 — Plan a trip

Open the app. The trip planner modal shows two tabs: **Driving** and **Transit**. Pick a route. The frontend calls `/plan`, which asks Agent 1 for dead zones along the route. Zones appear on the map.

### Step 2 — User A hits a dead zone

Click **Start Trip**. The dot moves along the route. When it enters a dead zone radius, the banner lights up ⚠️ and the frontend fires `POST /signal`. The orchestrator runs:

- Checks ClickHouse for a recent cached pack (cache hit → buy it, skip build)
- Runs 4 parallel web searches via Nimble (query type depends on route)
- Publishes a cited offline pack via Senso to a public URL
- Fires `deliver_pack` → banner goes ✅

Agent log panel streams every tool call with millisecond timing.

### Step 3 — User B hits the same zone

Switch to **Rider** in the top nav. Start their trip. Same route, same dead zone. This time the orchestrator finds the cached pack, fires a simulated agent-to-agent payment to User A, and delivers in ~1 second. The banner shows a "⚡ Saved pack found — instant delivery" card.

### Step 4 — Read the pack

Tap "Open Continuity Pack". The modal opens the `cited.md` page that Senso published — weather forecast, road conditions, points of interest, local news, all with live citations.

### Step 5 — Offline simulation

The countdown reaches zero and a brief "No Signal" overlay runs (30% of zone duration). When signal returns, a toast pops: "Back online · everything caught up".

### Step 6 — Replay

Every orchestration run is recorded as a full event trace. After a run completes, the **⏮ Replay** button re-streams the entire agent log at original timing — useful for demos and debugging.

---

## How the agent works

### Architecture

```
[Frontend]  →  POST /signal  →  [FastAPI]  →  orchestrator.py
                                                     |
                              ┌──────────────────────┤
                              ↓                      ↓
                      _run_with_llm()        _run_scripted()
                      (OpenRouter key)       (no API key)
                              |                      |
                         OpenAI tool-calling loop    |
                              └─────────┬────────────┘
                                        ↓
                            nimble_search × N  (parallel)
                            senso_publish
                            clickhouse_save_pack
                            payments_pay  (cache-hit path)
                            deliver_pack
                                        |
                              [WebSocket /ws]  →  Frontend log panel
```

### LLM-driven path

The orchestrator is **not a hardcoded pipeline.** It's an OpenAI function-calling loop — the LLM is given 7 tools as JSON schemas and decides which to call, in what order, with what arguments.

```python
for _ in range(8):
    resp = await client.chat.completions.create(
        model=_MODEL, messages=messages, tools=TOOLS,
        tool_choice="auto", parallel_tool_calls=True, temperature=0,
    )
    # run all tool_calls in parallel, append results as role="tool" messages
    # stop when model returns plain text or ctx.delivered is True
```

Every tool wrapper emits `tool_start` / `tool_end` WebSocket events with millisecond timestamps — that's the waterfall you see in the log panel.

### Route-type-aware content

The system prompt classifies each route into one of four types and instructs the LLM to use different Nimble queries accordingly:

| Route type | Example | Search focus |
|---|---|---|
| **Transit** | NYC L train, BART | Service alerts, delay updates, commuter news |
| **Mountain** | US-550 / Red Mountain Pass | High-elevation weather, CDOT road closures, SAR emergency contacts, avalanche advisories |
| **Long rural** | US-50 Nevada (15+ min dead zone) | 4-hour weather forecast, NDOT/UDOT road conditions, last fuel services before the zone |
| **Urban tunnel / default** | Lincoln Tunnel | Standard weather + road + POI + local news (depth scales with duration) |

The **scripted fallback** (no OpenRouter key) applies the same classification deterministically:

```python
transit    = is_transit_route(route_label)
mountain   = _is_mountain_route(route_label)
long_rural = _is_long_rural_route(route_label, dur_min)
```

Mountain routes always run 4 searches regardless of duration, because safety content (emergency contacts, SAR sheriff numbers, elevation forecasts) is critical. Short transit tunnels may only need 2.

### Tools exposed to the LLM

| Tool | Purpose |
|---|---|
| `clickhouse_find_recent_pack` | Cache lookup — called first, always |
| `nimble_search(query, topic)` | Web search for one topic (weather/road/poi/news) |
| `senso_publish(title, sections)` | Publish cited pack to public URL |
| `clickhouse_save_pack` | Persist pack for future buyers |
| `payments_pay` | Agent-to-agent settlement (cache-hit path) |
| `clickhouse_log_event` | Telemetry (built / bought / delivered) |
| `deliver_pack` | Final step — notifies the frontend |

### Pack quality evaluation

After every delivery, an async scorer runs:

```
score = coverage (40%) + SLA pass (40%) + completion (20%) - error penalty
```

- **Coverage:** which tool categories were called (search, publish, cache, deliver)
- **SLA pass:** pack delivered in under 85% of the eta_seconds window
- **Completion:** `deliver_pack` was called with no tool errors
- **Error penalty:** -5 pts per tool error, capped at -30

The score appears as a small badge on the ReadyCard (green ≥80, amber ≥60, red <60).

### Agent-to-agent payments

When User B hits a dead zone that User A's pack already covers:

1. The orchestrator finds the cached pack via ClickHouse
2. Calls `payments_pay` from `agent_b` → `agent_a` for $0.02
3. Delivers the cached pack in ~1 second
4. Dashboard ticks: `trips covered · instant packs · $0.02 paid`

The payment is simulated (fake tx hash, no on-chain dependencies). The settlement mechanism is modelled on x402-style agent-to-agent micropayments — the principle being that agents can transact for already-done work without rebuilding it.

---

## Observability via Datadog LLM Observability

Every run appears in [Datadog LLM Observability](https://docs.datadoghq.com/llm_observability/) as a single trace:

```
workflow: deadzone_signal
  └── agent: pack_builder
        ├── llm: openai.chat.completions.create   (auto-instrumented)
        ├── tool: clickhouse_find_recent_pack
        ├── llm: openai.chat.completions.create
        ├── tool: nimble_search × 4               (parallel)
        ├── tool: senso_publish
        ├── tool: clickhouse_save_pack
        ├── tool: payments_pay                    (cache-hit path)
        └── tool: deliver_pack
```

SDK usage:
- `LLMObs.enable(agentless_enabled=True)` at startup — no Datadog Agent process needed
- `@workflow / @agent / @tool` decorators on `orchestrator.run`, `_run_with_llm`, and each tool
- Auto-instrumentation of the OpenAI SDK — every `chat.completions.create` becomes an LLM span with prompt, response, token counts, latency
- `LLMObs.annotate(input_data=, output_data=, metadata=, tags=)` inside each tool so spans carry meaningful context

If `DD_API_KEY` is absent, all decorators no-op and the demo runs identically.

Where to look: **LLM Observability → Applications → `deadzone-agent`**

---

## Frontend

### Main demo (`/`)

Full-screen map with:
- Animated user dot moving along the selected route
- Dead zone circles plotted on the map
- **Overlay cards:** Alert → Preparing → (Cached Found) → Ready
- **Countdown banner:** live timer + pack status
- **Agent log panel** (right drawer): streams every tool_start/tool_end event with timing; can be hidden
- **Offline simulation overlay:** plays when the dot enters a dead zone
- **Pack modal:** opens the published cited.md page inline
- **Replay button:** re-streams the last trace at original timing
- **Dashboard strip** (bottom): trips covered, instant packs, avg ready time, sponsor labels
- **User switcher:** Driver (user_a) / Rider (user_b)

### Mobile features page (`/mobile`)

A scroll-snapped product landing page showing 6 features with phone mockups. Designed to show what the native iOS/Android app would look like.

| # | Feature | What it shows |
|---|---|---|
| 01 | GPS Auto-Detection | Route detected silently (BART: Embarcadero → SFO mockup) |
| 02 | Dead Zone Countdown | Lock screen + CarPlay (Ouray → Durango, US-550) + Watch |
| 03 | Contact Alerts | iMessage/SMS/email before going dark, location pin |
| 04 | Traffic Detection | BQE reroute for drivers; tunnel station mapping for transit riders |
| 05 | AI Content Pre-fetch | 22 min staged for a 20-min tunnel; 1 hour for Nevada desert |
| 06 | Seamless Return | Auto-sync on restore: messages, nav, podcast, articles |

Desktop: phone + description side by side. Mobile: snap panels (phone first, then description).

---

## Tech stack

| Layer | Tech |
|---|---|
| **Backend** | Python 3.12 · FastAPI · OpenAI SDK (function calling via OpenRouter) · `httpx` · WebSockets |
| **Frontend** | Next.js 14 (App Router) · TypeScript · Tailwind · `react-leaflet` |
| **Storage** | ClickHouse Cloud (free tier) with in-memory fallback |
| **Observability** | Datadog LLM Observability (`ddtrace`) |
| **Web search** | Nimble SERP API — falls back to LLM-generated route-specific stubs when key is absent |
| **Publish** | Senso (cited.md) — falls back to local static file server |
| **LLM** | OpenRouter → `google/gemini-2.0-flash-001` (configurable via `OPENAI_MODEL`) |

---

## Repo layout

```
deadzone/
├── backend/
│   ├── main.py                    # FastAPI app — /signal, /plan, /ws, /dashboard, /trace/*
│   ├── bus.py                     # WebSocket broadcast bus
│   ├── seed.py                    # Pre-seed packs/events so the dashboard isn't empty on first load
│   ├── schema.sql                 # ClickHouse DDL
│   ├── requirements.txt
│   └── tools/
│       ├── orchestrator.py        # LLM tool-calling loop, scripted fallback, quality evaluator
│       ├── agent1.py              # Route dead-zone prediction (Agent 1 integration + stub)
│       ├── nimble.py              # Web search — Nimble API, LLM stub, generic stub (8 handlers)
│       ├── senso.py               # Pack publish — Senso API, static-file fallback
│       ├── clickhouse_db.py       # Cache + telemetry + trace storage
│       ├── payments.py            # Simulated agent-to-agent payment
│       └── datadog.py             # LLMObs initialisation
└── frontend/
    ├── app/
    │   ├── page.tsx               # Main demo — map, log panel, overlays, trip planner
    │   └── mobile/page.tsx        # Product landing — 6 features with phone mockups
    ├── lib/route.ts               # Route types, polylines, dead zone definitions, haversine
    └── components/
        ├── TripPlanner.tsx        # Route selector (Driving / Transit tabs), plan → start flow
        ├── Map.tsx                # react-leaflet map with dots, zones, polyline
        ├── LiveLogs.tsx           # Agent event stream with waterfall timing
        ├── OverlayCard.tsx        # Alert / Preparing / CachedFound / Ready cards
        ├── Dashboard.tsx          # Bottom stats strip
        ├── CountdownBanner.tsx    # Live countdown to dead zone entry
        ├── PackModal.tsx          # Inline iframe for the published pack
        ├── OfflineOverlay.tsx     # "No Signal" simulation during zone traversal
        ├── OfflinePill.tsx        # Persistent "offline" pill during zone
        └── Toast.tsx              # Payment / synced / reconnecting toasts
```

---

## Quick start

```bash
# 1. Backend
cd backend
cp .env.example .env
# Fill in whichever keys you have — everything has a fallback (see below)
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 2. Frontend (new terminal)
cd frontend
npm install
npm run dev

# 3. Open http://localhost:3000
```

### Environment variables

| Variable | Required | Fallback |
|---|---|---|
| `OPENROUTER_API_KEY` | No | Scripted deterministic flow (same result, no LLM) |
| `NIMBLE_API_KEY` | No | LLM-generated route-specific stubs; generic stubs if LLM also absent |
| `SENSO_API_KEY` | No | Pack published to local `/static/packs/` directory |
| `CLICKHOUSE_HOST/USER/PASSWORD` | No | In-memory dict (resets on restart) |
| `DD_API_KEY` | No | All `@workflow/@agent/@tool` decorators no-op silently |
| `AGENT1_URL` | No | Built-in route prediction stub |
| `PUBLIC_BASE_URL` | No | Defaults to `http://localhost:8000` |
| `OPENAI_MODEL` | No | Defaults to `google/gemini-2.0-flash-001` |

**Zero keys required.** Every component has a deterministic fallback so the full demo flow runs end-to-end with an empty `.env`.

---

## API reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/signal` | Frontend reports user approaching dead zone; spawns orchestrator in background |
| `POST` | `/plan` | Predict dead zones for a route (Agent 1); returns zone list + emits `zones_ready` via WS |
| `POST` | `/run_pipeline` | Full Agent 1 → Agent 2 chain; builds packs for all zones in parallel |
| `GET` | `/dashboard` | Aggregate stats: trips covered, instant packs, avg build time, total paid |
| `GET` | `/traces` | List all trace IDs (most recent first) |
| `GET` | `/trace/{trace_id}` | Full event list for one trace (for replay UI) |
| `GET` | `/replay/{trace_id}` | SSE stream of trace events at original timing |
| `WS` | `/ws` | Real-time event stream: tool_start, tool_end, payment, pack_ready, eval_complete |

---

## What's real vs. simulated

| Feature | Status |
|---|---|
| LLM function-calling loop | Real (OpenRouter / Gemini 2.0 Flash) |
| Web search | Real (Nimble SERP API) — LLM stub when key absent |
| Pack publishing | Real (Senso cited.md) — local static fallback |
| Cache & telemetry | Real (ClickHouse Cloud) — in-memory fallback |
| Datadog LLM Observability | Real (`ddtrace`, agentless) — no-ops if key absent |
| Agent-to-agent payment | Simulated — fake tx hash, no on-chain dependencies |
| Route dead-zone prediction | LLM stub (Agent 1 integration point present) |
| Offline simulation | Simulated UI overlay (30% of zone duration) |
| Native iOS/Android app | Not built — `/mobile` shows what it would look like |

---

## UX decisions

This project went through an **18-reviewer study** (9 routes × 2 personas — desktop driver and mobile/transit rider). Key findings and fixes:

- **Transit riders were not represented.** Every default example (GPS mockup, CarPlay, traffic screen) assumed a car. All 6 feature descriptions now explicitly address both drivers and transit riders. Phone mockups updated to BART and BQE examples.
- **Technical jargon removed throughout.** "Nimble Network" → "Signal Guard". "Autonomous agents" → removed. "x402 pay" → hidden from all user-facing surfaces. "Awaiting agent activity" → "ready to scan your route". "Weak connectivity predicted" → "Signal drops soon — we're preparing your pack".
- **Scale mismatch.** Feature 05 copy now distinguishes a 20-min subway tunnel from an 80-min Nevada dead zone — the content staging amount is different and that needed to be said explicitly.
- **Emergency content for mountain routes.** US-550 and PCH reviewers flagged that generic content was useless at altitude. Mountain routes now always include SAR emergency contacts, county sheriff numbers, CDOT/CAIC advisories, and elevation-specific weather.
- **Empty log state.** The `??` emoji in the empty agent log looked broken to most reviewers. Replaced with `📡` and plain-language idle copy.
- **Footer credibility.** Hackathon branding dominated the footer of the mobile page. Redesigned product-first with the hackathon credit moved to a tiny footnote.

---

## Status

Hackathon project — Agentic Engineering Hack · Datadog NYC · May 2026.

No production hardening, no auth, no Docker. The point is to show a real LLM-driven agent loop using sponsor APIs (Nimble, Senso, Datadog) that falls back gracefully, and demonstrates a believable agent-to-agent economy in under three minutes.
