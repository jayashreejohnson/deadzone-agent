# DeadZone

> An AI agent that builds you a cited offline content pack right before you lose signal, and sells it to the next person who hits the same dead zone.

---

## The problem

You're driving through the Million Dollar Highway. Or riding BART from Embarcadero to SFO. Or taking the L train under the East River. Every time, the same thing happens: by the time the bars drop you've already lost the weather, the road conditions, the news, the directions, all of it. You only notice once it's too late.

DeadZone fixes that. It detects the dead zone before you reach it, builds a complete cited offline pack, and delivers it to every screen you have before you lose signal.

---

## What it does

When a user is about 4 minutes from a known dead zone, the agent wakes up and:

```
detect dead zone  ->  LLM reasons about what you'll need
       |
       searches the web (weather, roads, POIs, local news)
       |
       publishes a cited offline-readable pack to a public URL
       |
       caches each source page inline so the pack reads with no signal
       |
       delivers it to your device before you lose signal
```

The UI shows a banner transition: alert, preparing, ready. A live log panel streams every tool call the agent makes. Tap the banner to open the pack.

---

## Routes

DeadZone ships with **8 pre-built routes**, 6 driving and 2 transit, selectable from the trip planner:

**Driving**
- Manhattan to Newark (Lincoln Tunnel)
- Denver to Vail (Eisenhower Tunnel, Vail Pass)
- Los Angeles to Las Vegas (Cajon Pass, Mojave Desert)
- Carmel to San Luis Obispo via Highway 1 (Big Sur, Bixby Bridge)
- Ely to Fallon via US-50 (the Loneliest Road in America)
- Ouray to Durango via US-550 (Million Dollar Highway, Red Mountain Pass)

**Transit**
- NYC L train (Canarsie Tunnel under the East River)
- BART Embarcadero to West Oakland (Transbay Tube)

Each route type drives a different content strategy. See [How the agent works](#how-the-agent-works) below.

---

## Demo flow

### Step 1, plan a trip

Open the app. The trip planner modal shows two tabs: **Driving** and **Transit**. Pick a route. The frontend calls `/plan`, which asks Agent 1 for dead zones along the route. Zones appear on the map.

### Step 2, user A hits a dead zone

Click **Start Trip**. The dot moves along the route. When it enters a dead zone radius, the banner lights up and the frontend fires `POST /signal`. The orchestrator runs:

- Checks ClickHouse for a recent cached pack (cache hit, buy it, skip the build)
- Runs 4 parallel web searches via Nimble (queries chosen by route type)
- Publishes a cited offline pack via Senso
- Fetches and caches every source page inline so the pack works without signal
- Fires `deliver_pack` and the banner goes ready

The agent log panel streams every tool call with millisecond timing.

### Step 3, user B hits the same zone

Switch to **Rider** in the top nav. Start their trip. Same route, same dead zone. This time the orchestrator finds the cached pack, fires a simulated agent-to-agent payment to User A, and delivers in about one second. The banner shows a "Saved pack found, instant delivery" card.

### Step 4, read the pack

Tap "Open Continuity Pack". The pack opens inline.

Each section has:
- A dense offline-readable summary with mile markers, exact addresses, phone numbers, in-tunnel radio frequencies, emergency procedures
- Tappable phone links (cellular voice works without data, so the user can actually call the sheriff or tunnel control while offline)
- A list of cited sources, each with a "Read cached page" accordion that expands to show the actual page content extracted at build time

If a source could not be cached (blocked by Cloudflare, paywall, JavaScript-only shell), it is hidden entirely. Every source in the pack is guaranteed readable offline.

### Step 5, offline simulation

The countdown reaches zero and a brief "No Signal" overlay runs (about 30% of zone duration). When signal returns, a toast pops: "Back online, everything caught up".

### Step 6, replay

Every orchestration run is recorded as a full event trace. After a run completes, the **Replay** button re-streams the entire agent log at original timing, useful for demos and debugging.

---

## How the agent works

### Architecture

```
[Frontend]  ->  POST /signal  ->  [FastAPI]  ->  orchestrator.run
                                                       |
                          mode = agentic / auto / scripted
                                                       |
                              _run_with_llm                _run_scripted
                              (LLM tool-calling loop)     (no LLM hops)
                                       |
                              ┌────────┴─────────────────┐
                              | iter 0: planning         |
                              |   LLM picks cache_find + |
                              |   nimble_search topics   |
                              | step: senso_publish      |
                              | step: clickhouse_save_pack|
                              | step: deliver_pack       |
                              └──────────────────────────┘
                                       |
                              if mid-flow LLM failure:
                                _finalize_from_messages
                                preserves LLM's iter-0 work
                                       |
                              [WebSocket /ws]  ->  Frontend log panel
```

### LLM-driven path

The orchestrator is **not a hardcoded pipeline.** It's an OpenAI function-calling loop where the LLM is given 7 tools as JSON schemas and decides which to call, in what order, with what arguments.

```python
# iter 0: planning step, full _PROMPT_CORE, all tools, tool_choice="auto"
resp = await _call_llm_with_fallback(plan_messages, tools=TOOLS, tool_choice="auto")
# LLM batches clickhouse_find_recent_pack + 4 nimble_search calls in parallel

# subsequent steps: tiny focused prompts + single forced tool
await _step_publish(signal, search_results, ctx)   # tool_choice forces senso_publish
await _step_save(signal, search_results, ctx)      # tool_choice forces clickhouse_save_pack
await _step_deliver(ctx.pack_url, False, ctx.pack_id, ctx)  # forces deliver_pack
```

Every tool wrapper emits `tool_start` and `tool_end` WebSocket events with millisecond timestamps. That's the waterfall you see in the log panel.

### Per-provider LLM resilience

The agent supports a 3-provider chain: OpenRouter (primary), Groq (fallback), Cerebras (final fallback). Each provider has its own circuit breaker with independent state.

```python
# Per-provider breaker state
llm_circuit.is_open("openrouter")     # check
llm_circuit.classify_and_trip(p, err) # trip with auto-classified cooldown
llm_circuit.reset("openrouter")       # close on success
```

**Failure classification:**
- Terminal (402 insufficient credits, 401 invalid key, no_credits, billing): tripped for `LLM_CIRCUIT_TERMINAL_COOLDOWN_SEC` (default 1 hour). These don't self-recover within a minute.
- Transient (429, 5xx, timeout): tripped for `LLM_CIRCUIT_COOLDOWN_SEC` (default 60 seconds).

**Per-provider tuning:**
- Each provider gets its own system prompt variant. Llama 3.3 70B on Groq gets prefixed schema-discipline framing. Cerebras gets a bare prompt to ride the queued free tier faster.
- `parallel_tool_calls` is enabled for Gemini and Llama, omitted for Cerebras's gpt-oss / GLM-4 (some Cerebras models reject the flag).
- Per-request timeout is 5 seconds (configurable). `max_retries=0` on the OpenAI SDK client so the timeout is the real hard cap.
- Forced `tool_choice` syntax is downgraded to `"required"` on Cerebras since `zai-glm-4.7` returns 400 on the granular `{type:function, function:{name:...}}` form.

**Writing style enforcement (applies to every LLM-generated string):**
- System prompts in every LLM caller (orchestrator planning, focused step prompts, nimble stub, agent1 prediction) include a hard rule: never use em dashes (U+2014) or en dashes (U+2013) in any output. Use commas, periods, colons, or hyphens. Plain ASCII punctuation only. No fancy quotes, no ellipsis character.
- Belt-and-suspenders: the `senso_publish` dispatcher scrubs em / en dashes out of title, section heading, summary, source title, and source snippet before publishing. Catches whatever slips past the prompt rule.

**Token budget management:**
- Iter 0 (planning) uses the larger model (`GROQ_MODEL`, default `llama-3.3-70b-versatile`).
- Per-step focused calls (publish, save, deliver) use the smaller model (`GROQ_MODEL_SMALL`, default `llama-3.1-8b-instant`) which has a separate daily quota bucket on Groq's free tier. This prevents iter 0 from starving the focused steps.
- Each focused step ships a tiny prompt (about 200 tokens) plus only the data needed for that one tool call, so a full pack build stays under 6,000 TPM on Groq's free tier.

### State-machine forcing

Free-tier LLMs sometimes stop mid-flow without calling `deliver_pack`. To prevent that, the orchestrator uses `tool_choice` to guarantee call sequence progression:

```
has searches but no pack_url   -> tool_choice forces senso_publish
has pack_url but no pack_id    -> tool_choice forces clickhouse_save_pack
has pack_id but not delivered  -> tool_choice forces deliver_pack
```

The LLM still chooses content (queries, summaries, pack sections, sources). The orchestrator only constrains the call sequence.

### Mid-flow finalizer

When the LLM tool loop fails partway through (provider 400, all breakers open, etc), the orchestrator does NOT restart the scripted flow from a cold cache_find. Instead `_finalize_from_messages` walks forward through any remaining steps using the work the LLM already produced (search results from iter 0). The model's content decisions are preserved. The orchestrator only fills in the deterministic publish, save, deliver steps the model could not complete itself.

### Route-type-aware content

The system prompt classifies each route into one of five types and instructs the LLM to use different Nimble queries accordingly:

| Route type | Example | Search focus |
|---|---|---|
| **Transit** | NYC L train, BART | Service alerts, delays, commuter news |
| **Mountain** | US-550 Red Mountain Pass | High-elevation weather, CDOT closures, SAR emergency contacts, avalanche advisories |
| **Long rural** | US-50 Nevada | 4-hour weather forecast, NDOT road conditions, last fuel services |
| **Urban tunnel** | Lincoln Tunnel | Weather + road + POI + local news, depth scales with duration |
| **Default highway** | any other | Standard 4-topic search |

### Tools exposed to the LLM

| Tool | Purpose |
|---|---|
| `clickhouse_find_recent_pack` | Cache lookup, called first, always |
| `nimble_search(query, topic)` | Web search for one topic (weather / road / poi / news) |
| `senso_publish(title, sections)` | Publish cited pack to public URL |
| `clickhouse_save_pack` | Persist pack for future buyers |
| `payments_pay` | Agent-to-agent settlement (cache-hit path) |
| `clickhouse_log_event` | Telemetry (built, bought, delivered) |
| `deliver_pack` | Final step, notifies the frontend |

### Pack quality evaluation

After every delivery, an async scorer runs:

```
score = coverage (40%) + SLA pass (40%) + completion (20%) - error penalty
```

- **Coverage:** which tool categories were called (search, publish, cache, deliver)
- **SLA pass:** pack delivered in under 85% of the eta_seconds window
- **Completion:** `deliver_pack` was called with no tool errors
- **Error penalty:** -5 points per tool error, capped at -30

The score appears as a small badge on the ReadyCard (green if 80 or above, amber if 60 or above, red below 60).

### Agent-to-agent payments

When User B hits a dead zone that User A's pack already covers:

1. The orchestrator finds the cached pack via ClickHouse
2. Calls `payments_pay` from `agent_b` to `agent_a` for $0.02
3. Delivers the cached pack in about one second
4. Dashboard ticks: trips covered, instant packs, total paid

The payment is simulated (fake tx hash, no on-chain dependencies). The settlement mechanism is modelled on x402-style agent-to-agent micropayments: agents can transact for already-done work without rebuilding it.

---

## Pack content strategy

The pack is the offline copy of the web content, not a list of links to it. Three layers stack to make the pack actually useful in a dead zone:

### Layer 1: curated offline-readable summary

Each section leads with a dense plain-text summary that carries the actionable content the user needs without any network:

- Mile markers and exit numbers for every service stop
- Real phone numbers (CHP, county sheriff, search and rescue, hospital, tunnel control), auto-rendered as tappable `tel:` links so the user can call from inside a dead zone (cellular voice does not need data)
- In-tunnel radio frequencies (AM 1630 Lincoln, AM 1610 Eisenhower) for live closure updates
- Emergency procedure step-by-step (pull right, use white phones every 300 ft; use yellow CHP boxes every 5 mi; in summer heat stay WITH the vehicle)
- Recurring traffic timing (Sunday slog 3 to 8 PM on I-70, Friday Vegas-bound at Primm)
- Toll prices, speed limits, lane configs, chain laws

The curated content is wrapped in a `_ZONE_SOURCES` lookup keyed by zone name or route alias, so "Manhattan to Newark" resolves to the Lincoln Tunnel curated entry even when the LLM query doesn't include the literal zone name.

### Layer 2: cached webpage snapshots

During `senso_publish`, every source URL is fetched in parallel and the main article content is extracted via BeautifulSoup. The sanitized HTML is embedded inline in the pack as a `<details>` accordion. The user taps "Read cached page" and the page content unfolds inline. No network required.

Rejection criteria for cached snapshots:
- HTTP non-2xx
- Non-HTML content-type
- Bot-block / WAF / paywall body patterns (about 70 phrases across categories: Cloudflare challenge, PerimeterX, DataDome, Sucuri, Incapsula, Akamai bot manager, F5 Networks, hCaptcha / reCAPTCHA / Turnstile, "Subscribe to continue", "Please verify you are human", "Performance and security by Cloudflare", "Attention required", "DDoS protection", "Ray ID", site maintenance / "we'll be right back", etc.)
- Extracted main-content shorter than 500 characters (catches JavaScript-only shells where bs4 sees only the empty `<body>`)
- Block phrases inside the extracted content itself (catches embedded "you've reached your free article limit" notices that only appear in the article block, not the page shell)

The reachability check in `nimble.py` runs a parallel sweep with about 30 of the same patterns against the first 4 KB of every source URL before the LLM ever sees them, so a CF-challenged URL is marked `reachable: False` up front and skipped at fetch time too.

### Layer 3: strict source rendering

The renderer only shows sources where BOTH the reachability check passed AND a successful cached snapshot exists. If our scraper could not pull clean content, the source is hidden entirely. No dead rows, no fake "Read cached page" buttons that would open a Cloudflare challenge. Every source displayed in the pack is guaranteed to read offline.

Sections whose entire source list got filtered out still render correctly: the curated offline-readable summary at the top of each section is the primary value, the source list is supplementary. An empty source list under a fully-formed section is the cleanest possible failure mode for a blocked authority page.

---

## Observability via Datadog LLM Observability

Every run appears in [Datadog LLM Observability](https://docs.datadoghq.com/llm_observability/) as a single trace:

```
workflow: deadzone_signal
  agent: pack_builder
    llm: openai.chat.completions.create   (auto-instrumented)
    tool: clickhouse_find_recent_pack
    llm: openai.chat.completions.create
    tool: nimble_search x 4               (parallel)
    tool: senso_publish
    tool: clickhouse_save_pack
    tool: payments_pay                    (cache-hit path)
    tool: deliver_pack
```

SDK usage:
- `LLMObs.enable(agentless_enabled=True)` at startup, no Datadog Agent process needed
- `@workflow`, `@agent`, `@tool` decorators on `orchestrator.run`, `_run_with_llm`, and each tool
- Auto-instrumentation of the OpenAI SDK, every `chat.completions.create` becomes an LLM span with prompt, response, token counts, latency
- `LLMObs.annotate(input_data=, output_data=, metadata=, tags=)` inside each tool so spans carry meaningful context

If `DD_API_KEY` is absent, all decorators no-op and the demo runs identically.

Where to look: **LLM Observability, Applications, `deadzone-agent`**

---

## Frontend

### Main demo (`/`)

Full-screen map with:
- Animated user dot moving along the selected route
- Dead zone circles plotted on the map
- **Overlay cards:** Alert, Preparing, (Cached Found), Ready
- **Countdown banner:** live timer + pack status
- **Agent log panel** (right drawer): streams every tool_start / tool_end event with timing, can be hidden
- **Offline simulation overlay:** plays when the dot enters a dead zone
- **Pack modal:** opens the published pack inline
- **Replay button:** re-streams the last trace at original timing
- **Dashboard strip** (bottom): trips covered, instant packs, avg ready time, sponsor labels
- **User switcher:** Driver (user_a) and Rider (user_b)

The map uses memoized static layers (route polyline + dead-zone circles) so the trip animation (which updates user position about three times per second) doesn't re-create Leaflet layers on every tick. Without this the whole map would flash on every dot movement.

### Mobile responsiveness

On viewports under 768px wide:
- The 300px log drawer auto-collapses on first render and slides over the map rather than pushing content
- AlertCard buttons stack vertically: Prepare Pack full-width on top, Reroute / Stay split underneath
- StatTile grid drops to one column
- PackModal uses 12px side padding and 92vh height instead of 48px and 88vh

### Mobile features page (`/mobile`)

A scroll-snapped product landing page showing 6 features with phone mockups. Designed to show what the native iOS/Android app would look like.

| # | Feature | What it shows |
|---|---|---|
| 01 | GPS Auto-Detection | Route detected silently (BART Embarcadero to SFO mockup) |
| 02 | Dead Zone Countdown | Lock screen, CarPlay (Ouray to Durango), Watch |
| 03 | Contact Alerts | iMessage / SMS / email before going dark, location pin |
| 04 | Traffic Detection | BQE reroute for drivers; tunnel station mapping for transit riders |
| 05 | AI Content Pre-fetch | 22 min staged for a 20-min tunnel; 1 hour for Nevada desert |
| 06 | Seamless Return | Auto-sync on restore: messages, nav, podcast, articles |

Desktop: phone + description side by side. Mobile: snap panels (phone first, then description).

---

## Tech stack

| Layer | Tech |
|---|---|
| **Backend** | Python 3.12, FastAPI, OpenAI SDK (function calling), httpx, WebSockets, BeautifulSoup4 |
| **Frontend** | Next.js 14 (App Router), TypeScript, Tailwind, react-leaflet |
| **Storage** | ClickHouse Cloud (free tier) with in-memory fallback |
| **Observability** | Datadog LLM Observability (ddtrace) |
| **Web search** | Nimble SERP API, falls back to LLM-generated route-specific stubs, falls back to curated zone-aware stubs |
| **Publish** | Senso (cited.md), falls back to local static file server |
| **LLM providers** | OpenRouter (`google/gemini-2.0-flash-001`) -> Groq (`llama-3.3-70b-versatile` + `llama-3.1-8b-instant`) -> Cerebras (`zai-glm-4.7` / `gpt-oss-120b`), with per-provider circuit breakers |
| **Snapshot extraction** | BeautifulSoup4 with tag whitelist, plus a 50-phrase bot-block / WAF / paywall reject list |

---

## Repo layout

```
deadzone/
|- backend/
|  |- main.py                    # FastAPI app: /signal, /plan, /ws, /dashboard, /trace/*, /llm-check, /llm-circuit/reset
|  |- bus.py                     # WebSocket broadcast bus
|  |- seed.py                    # Pre-seed packs/events so the dashboard isn't empty on first load
|  |- schema.sql                 # ClickHouse DDL
|  |- requirements.txt
|  |- tools/
|     |- orchestrator.py         # LLM tool-calling loop, per-step focused calls, mid-flow finalizer, scripted fallback, quality evaluator
|     |- agent1.py               # Route dead-zone prediction with shared circuit breaker
|     |- nimble.py               # Web search: Nimble API, LLM stub, curated zone-aware stubs with bot-block-aware reachability check
|     |- senso.py                # Pack publish: Senso API, static fallback, cached snapshot fetcher with WAF detection
|     |- clickhouse_db.py        # Cache + telemetry + trace storage
|     |- payments.py             # Simulated agent-to-agent payment
|     |- llm_circuit.py          # Per-provider circuit breaker (terminal vs transient cooldowns)
|     |- datadog.py              # LLMObs initialisation
|- frontend/
   |- app/
   |  |- page.tsx                # Main demo: map, log panel, overlays, trip planner
   |  |- mobile/page.tsx         # Product landing: 6 features with phone mockups
   |- lib/route.ts               # Route types, polylines, dead zone definitions, haversine
   |- components/
      |- TripPlanner.tsx         # Route selector (Driving / Transit tabs), plan to start flow
      |- Map.tsx                 # react-leaflet map with memoized static layers
      |- LiveLogs.tsx            # Agent event stream with waterfall timing
      |- OverlayCard.tsx         # Alert / Preparing / CachedFound / Ready cards
      |- Dashboard.tsx           # Bottom stats strip
      |- CountdownBanner.tsx     # Live countdown to dead zone entry
      |- PackModal.tsx           # Inline iframe for the published pack
      |- OfflineOverlay.tsx      # No Signal simulation during zone traversal
      |- OfflinePill.tsx         # Persistent offline pill during zone
      |- Toast.tsx               # Payment / synced / reconnecting toasts
```

---

## Quick start

```bash
# 1. Backend
cd backend
cp .env.example .env
# Fill in whichever keys you have; everything has a fallback (see below)
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 2. Frontend (new terminal)
cd frontend
npm install
npm run dev

# 3. Open http://localhost:3000
```

### Environment variables

| Variable | Required | Default / Fallback |
|---|---|---|
| `OPENROUTER_API_KEY` | No | Falls through to Groq, then Cerebras, then scripted |
| `OPENAI_MODEL` | No | `google/gemini-2.0-flash-001` |
| `GROQ_API_KEY` | No | Same fallthrough |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` (used for planning) |
| `GROQ_MODEL_SMALL` | No | `llama-3.1-8b-instant` (used for focused steps, separate quota bucket) |
| `CEREBRAS_API_KEY` | No | Same fallthrough |
| `CEREBRAS_MODEL` | No | `llama-3.3-70b` |
| `NIMBLE_API_KEY` | No | LLM-generated route-specific stubs, then curated zone-aware stubs |
| `SENSO_API_KEY` | No | Pack published to local `/static/packs/` directory |
| `CLICKHOUSE_HOST/USER/PASSWORD` | No | In-memory dict (resets on restart) |
| `DD_API_KEY` | No | All `@workflow`, `@agent`, `@tool` decorators no-op silently |
| `AGENT1_URL` | No | Built-in route prediction stub |
| `PUBLIC_BASE_URL` | No | `http://localhost:8000` |
| `ORCHESTRATOR_MODE` | No | `agentic`, options: `agentic` / `auto` / `scripted` |
| `LLM_TIMEOUT_SEC` | No | `5` |
| `LLM_CIRCUIT_COOLDOWN_SEC` | No | `60` (transient failures) |
| `LLM_CIRCUIT_TERMINAL_COOLDOWN_SEC` | No | `3600` (402, 401, billing) |
| `PACK_SNAPSHOT_TIMEOUT_SEC` | No | `6` |
| `PACK_SNAPSHOT_MAX_CHARS` | No | `6000` |

**Zero keys required.** Every component has a deterministic fallback so the full demo flow runs end-to-end with an empty `.env`.

---

## API reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/signal` | Frontend reports user approaching dead zone, spawns orchestrator in background |
| `POST` | `/plan` | Predict dead zones for a route (Agent 1), returns zone list and emits `zones_ready` via WS |
| `POST` | `/run_pipeline` | Full Agent 1 to Agent 2 chain, builds packs for all zones in parallel |
| `GET` | `/dashboard` | Aggregate stats: trips covered, instant packs, avg build time, total paid |
| `GET` | `/traces` | List all trace IDs (most recent first) |
| `GET` | `/trace/{trace_id}` | Full event list for one trace (for replay UI) |
| `GET` | `/replay/{trace_id}` | SSE stream of trace events at original timing |
| `GET` | `/llm-check` | Ping each configured LLM provider and report per-provider circuit breaker state |
| `GET` | `/llm-models` | List the actual model IDs each configured provider exposes for our API key (useful when a 404 model_not_found suggests we're guessing wrong IDs) |
| `POST` | `/llm-circuit/reset` | Manually close all per-provider breakers (e.g. after refilling Groq tokens) |
| `WS` | `/ws` | Real-time event stream: tool_start, tool_end, payment, pack_ready, eval_complete |

---

## What's real vs simulated

| Feature | Status |
|---|---|
| LLM function-calling loop | Real, with OpenRouter, Groq, Cerebras chain and per-provider circuit breakers |
| Web search | Real (Nimble SERP API), falls back to LLM stub, falls back to curated zone-aware stubs |
| Pack publishing | Real (Senso cited.md), local static fallback |
| Cached page snapshots | Real (httpx + BeautifulSoup4 extraction, embedded inline in the pack HTML) |
| Cache and telemetry | Real (ClickHouse Cloud), in-memory fallback |
| Datadog LLM Observability | Real (ddtrace agentless), no-ops if key absent |
| Agent-to-agent payment | Simulated, fake tx hash, no on-chain dependencies |
| Route dead-zone prediction | LLM stub (Agent 1 integration point present) with shared circuit breaker |
| Offline simulation | Simulated UI overlay (about 30% of zone duration) |
| Native iOS / Android app | Not built, `/mobile` shows what it would look like |

---

## UX decisions

This project went through an **18-reviewer study** (9 routes by 2 personas, desktop driver and mobile transit rider). Key findings and fixes:

- **Transit riders were not represented.** Every default example (GPS mockup, CarPlay, traffic screen) assumed a car. All 6 feature descriptions now explicitly address both drivers and transit riders. Phone mockups updated to BART and BQE examples.
- **Technical jargon removed throughout.** "Nimble Network" became "Signal Guard". "Autonomous agents" was removed. "x402 pay" hidden from all user-facing surfaces. "Awaiting agent activity" became "ready to scan your route". "Weak connectivity predicted" became "Signal drops soon, we're preparing your pack".
- **Scale mismatch.** Feature 05 copy now distinguishes a 20-min subway tunnel from an 80-min Nevada dead zone, the content staging amount is different and that needed to be said explicitly.
- **Emergency content for mountain routes.** US-550 and PCH reviewers flagged that generic content was useless at altitude. Mountain routes now always include SAR emergency contacts, county sheriff numbers, CDOT / CAIC advisories, and elevation-specific weather.
- **Pack content rebuilt from scratch.** Reviewers said the old packs were "kinda trash": generic homepage URLs (google.com/maps, weather.com), boilerplate summaries ("no major incidents reported"), nothing zone-specific. Rebuilt as curated offline-readable text with mile markers, real phone numbers, in-tunnel radio frequencies, exact service stops, emergency procedure, plus inline cached snapshots of each source page.
- **Empty log state.** The `??` emoji in the empty agent log looked broken to most reviewers. Replaced with a signal icon and plain-language idle copy.

---

## Status

Hackathon project, Agentic Engineering Hack, Datadog NYC, May 2026.

No production hardening, no auth, no Docker. The point is to show a real LLM-driven agent loop using sponsor APIs (Nimble, Senso, Datadog) with per-provider circuit breakers, agent-to-agent payments, and packs that actually work offline in under three minutes.
