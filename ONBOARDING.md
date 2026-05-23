# Hackathon Onboarding — Agentic Engineering Hack
# May 23, Datadog NYC | Deadline: 4:30 PM sharp

---

## The Track

**Context Engineering Challenge — Build agents that act on the web**

> Ship an autonomous agent that does real work on the open web.
> Agents must take real action (publish, monitor, orchestrate, transact), grounded in real sources. Use 2+ sponsor tools.

---

## Our Project: Dead Zone Content Agent

### The Problem
Everyone has experienced cellular dead zones. Current systems react AFTER signal drops — they buffer, degrade, fail. Nobody predicts dead zones ahead of time and prepares for them.

### The Idea
A two-agent AI system that:
1. **Predicts** dead zones on your route before you hit them
2. **Autonomously fetches** real content from the web so offline playback is ready before signal drops

### User Story
> "I'm driving Manhattan to Newark at 5pm. The agent detects a 3-minute dead zone at Lincoln Tunnel at 5:12pm. While I still have signal, it fetches a podcast clip and caches navigation. I hit the tunnel — nothing freezes."

### Why It Fits the Track
- Real action on the open web: Nimble scrapes real articles/podcasts
- Grounded in real sources: ClickHouse signal data + Nimble real URLs
- Autonomous: agent reasons about WHICH content, WHEN to fetch, WHAT fits the window
- Context engineering: Agent 1 builds dead zone context → hands to Agent 2 → Agent 2 acts

---

## Prize Targets (aim for all three)

| Sponsor | Prize | Our Integration |
|---------|-------|----------------|
| **Nimble** | $1,500 (1st: $1k Amazon + $1k credits) | Agent 2 fetches real web content via Nimble |
| **ClickHouse** | $1,000 (1st: $1k cash + $500 credits) | Agent 1 queries signal history from ClickHouse |
| **Senso.ai** | $3,000 credits | Knowledge base for known dead zone patterns |

---

## Sponsor Tools & How We Use Them

### Nimble — Web Scraping / Content Fetching
- Agent 2 calls Nimble to fetch real articles and podcast clips from the open web
- Matches content length to dead zone duration (3+ min → article, 1-2 min → podcast clip)
- Sign up: nimbleway.com

### ClickHouse — Signal History Database
- Stores historical cellular signal quality data (location, strength, timestamp)
- Agent 1 queries this to identify dead zone patterns on a given route
- Sign up: clickhouse.com/cloud (free tier)

### Senso.ai — Context Layer / Knowledge Base
- Stores verified knowledge about known dead zones (pre-loaded patterns, route-specific rules)
- Agent 1 queries Senso FIRST for known dead zones before hitting ClickHouse for historical data
- Install CLI: `npm install -g @senso-ai/cli`
- Docs: docs.senso.ai

### Datadog Lapdog — LLM Observability
- Runs on localhost:8126, captures every span, prompt, tool call, and cost
- Install: `pipx install ddapm-test-agent`
- Run: `lapdog python main.py`
- Shows judges a real trace UI of agent decisions — huge demo value

### Google DeepMind / Gemini 2.0 Flash
- Reasoning engine for both agents
- Accessed via OpenRouter (API key already in .env)
- Model: `google/gemini-2.0-flash-001`

---

## Architecture

```
Agent 1 — Prediction Agent
  input:  route + departure time
  tools:  query_senso_knowledge, query_signal_history, predict_dead_zones
  output: structured dead zone list (location, start_time, duration_minutes, severity)

        ↓ HANDOFF (agent1_output injected into agent2 user message)

Agent 2 — Content Curation Agent
  input:  dead zone predictions from Agent 1
  tools:  fetch_content (via Nimble), queue_content
  output: content queue ready for offline playback
```

---

## Tech Stack

```
Backend:   Python, FastAPI, raw OpenAI client (NO frameworks)
Frontend:  Streamlit
Database:  ClickHouse Cloud (free tier)
Scraping:  Nimble API
Knowledge: Senso.ai
Model:     Gemini 2.0 Flash via OpenRouter
Observ:    Datadog Lapdog (localhost:8126)
```

---

## Environment Setup

```bash
# 1. Copy the .env file (Shageenth has the OpenRouter key)
cp /mnt/c/Users/shage/let-us-git-along/.env ~/FOLDER_NAME/.env

# 2. Create and activate virtual environment
python3 -m venv ~/hackathon && source ~/hackathon/bin/activate

# 3. Install dependencies
pip install openai fastapi uvicorn streamlit clickhouse-connect python-dotenv

# 4. Install Lapdog
pipx install ddapm-test-agent

# 5. Install Senso CLI
npm install -g @senso-ai/cli
```

```python
# Every Python file loads env like this:
from dotenv import load_dotenv
import os

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
```

---

## The Core Agent Loop (use this exact pattern)

```python
from openai import OpenAI
import json

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
)

messages = [
    {"role": "system", "content": "Your agent's role and instructions"},
    {"role": "user", "content": "The goal"}
]

MAX_ITERATIONS = 50  # high — prompt handles stopping, this is just a safety net
iteration = 0

while iteration < MAX_ITERATIONS:
    iteration += 1
    response = client.chat.completions.create(
        model="google/gemini-2.0-flash-001",
        messages=messages,
        tools=tools
    )
    msg = response.choices[0].message

    if msg.tool_calls:
        messages.append(msg)                     # append ONCE before loop
        for tool_call in msg.tool_calls:         # loop ALL tool calls, never just [0]
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)
            try:
                result = your_functions[fn_name](**fn_args)
            except Exception as e:
                result = {"error": str(e), "status": "failed"}
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result)
            })
    else:
        agent_output = msg.content
        break
```

## The Handoff Pattern

```python
# Agent 1 finishes → inject output into Agent 2
messages_agent2 = [
    {"role": "system", "content": "Agent 2 system prompt..."},
    {"role": "user", "content": f"Here are the dead zones: {agent1_output}. Fetch content for each."}
]
```

---

## Working System Prompts

**Agent 1:**
```
You are a signal prediction expert. Analyze routes and identify dead zones using your tools.
Always include location, start_time, duration_minutes, and severity for each dead zone.
Your final conclusion will be passed directly to another AI agent — structure it clearly
so that agent can immediately act on it without ambiguity.
If a tool returns an error, do not retry — move on and work with what you have.
```

**Agent 2:**
```
You are a content curation agent. Given dead zone predictions, fetch appropriate content
for each dead zone based on its duration. Use these exact rules:
- 3+ minutes → fetch an article
- 1-2 minutes → fetch a podcast clip
- Always also cache navigation regardless of duration
If a tool returns an error, move on and summarize what you successfully fetched.
```

---

## Key Rules — DO NOT BREAK

1. **NO frameworks** — no LangChain, no AG2, no CrewAI, no AutoGen
2. **Raw OpenAI client only** for the agent loop
3. **For loop over ALL tool_calls** — never just handle `[0]`
4. **Append msg ONCE before the for loop** — results appended inside loop
5. **MAX_ITERATIONS = 50** — set high, prompt handles stopping
6. **NEVER use `response_format={"type": "json_object"}` with tools** — breaks tool calling
7. **Simulated data is fine** — tell judges upfront, architecture is what matters
8. **Tell agents WHO reads their output** — not HOW to format it

---

## Judging Criteria (20% each)

| Criteria | How we score |
|----------|-------------|
| **Autonomy** | Agent reasons about which content, when to fetch, what fits the window |
| **Idea** | Clear real-world problem, Nokia/telecom angle for pitch |
| **Technical Implementation** | Raw loop, real handoff, no frameworks |
| **Tool Use** | Nimble + ClickHouse + Senso + Lapdog |
| **Presentation** | 3-min demo recording — plan and record before 4:00 PM |

---

## Submission Checklist
- [ ] Public GitHub repo (create early, push often)
- [ ] 3-minute demo recording (record by 4:00 PM, submit by 4:30 PM)
- [ ] Both agents running end-to-end
- [ ] At least 2 sponsor tools wired in (aim for 3)
- [ ] Lapdog running during demo for observability trace

---

## 60-Second Pitch

> "We built a two-agent AI system that predicts cellular dead zones before you hit them and autonomously fetches real content from the web. Agent 1 queries our Senso knowledge base and ClickHouse signal history to predict dead zones with location, timing, and severity. It hands off to Agent 2 which uses Nimble to fetch real articles and podcast clips — matching content length to dead zone duration. Gemini is the reasoning engine. The whole system is built raw — no frameworks — so every decision the LLM makes is transparent. This is context engineering: the agent builds the right context before you lose connectivity."

---

## Division of Work

**Shageenth (backend):** Agent loop, tool functions, ClickHouse queries, Nimble integration, Senso integration, FastAPI server

**Friend (frontend):** Streamlit UI, simulated route data, demo polish, Lapdog trace screenshots for slides
