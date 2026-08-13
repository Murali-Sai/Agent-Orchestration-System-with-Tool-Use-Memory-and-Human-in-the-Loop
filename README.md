# Agent Orchestration System with Tool Use, Memory, and Human-in-the-Loop

> Production-grade multi-agent platform where a supervisor AI decomposes complex tasks, dispatches specialized agents with real tools, maintains persistent memory across sessions, and escalates to humans when confidence is low — with full observability into every decision.

[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://python.org)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-green)](https://langchain-ai.github.io/langgraph/)
[![OpenAI](https://img.shields.io/badge/LLM-GPT--4o-orange)](https://openai.com)
[![Supabase](https://img.shields.io/badge/DB-Supabase-darkgreen)](https://supabase.com)
[![Docker](https://img.shields.io/badge/Deploy-Docker-blue)](https://docker.com)

---

## What This Is

This is not a chatbot wrapper. It's **autonomous AI infrastructure** — the kind of system companies are actively building and hiring for.

A user submits a complex request. The system:
1. **Supervisor** decomposes it into an ordered subtask plan, informed by past memory
2. **Specialists** execute each subtask using real tools (web search, code execution, file I/O)
3. **Reviewer** scores the output and rejects low-quality results for rework
4. **Human-in-the-loop** pauses execution at sensitive steps for human approval
5. **Memory** saves lessons learned so the system gets smarter over time
6. **Observability** records every decision in a queryable trace

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User Request                            │
└─────────────────────┬───────────────────────────────────────┘
                      │
              ┌───────▼────────┐
              │   SUPERVISOR   │◄── Long-Term Memory (Supabase pgvector)
              │  (GPT-4o)      │    retrieves similar past tasks
              └───────┬────────┘
                      │ execution plan
          ┌───────────┼───────────┐
          │           │           │
   ┌──────▼───┐ ┌─────▼────┐ ┌───▼──────┐
   │ RESEARCH │ │ ANALYSIS │ │ WRITING  │  ◄── Specialist Agents
   │ web_search│ │exec_python│ │write_file│
   └──────┬───┘ └─────┬────┘ └───┬──────┘
          └───────────┼───────────┘
                      │ results
              ┌───────▼────────┐
              │    REVIEWER    │  scores quality 0–1
              └───────┬────────┘
                      │
           ┌──────────▼───────────────┐
           │  score ≥ threshold?      │
           │  YES      → finalize     │
           │  NO (1st) → rework ──────┼──► back to specialists
           │  NO (2nd) → HITL queue   │──► Human Review UI
           └──────────────────────────┘
                      │
              ┌───────▼────────┐
              │  SUPERVISOR    │  synthesizes final answer
              │  (synthesis)   │──► Saves to Long-Term Memory
              └────────────────┘

Rework loop: a first below-threshold score reopens every subtask with the
reviewer's feedback injected into the specialist prompt. Only a second failure
pulls in a human — automatic retry first, escalation second.

Persistent layer:
  Redis              → working memory (per-task, ephemeral)
  Supabase pgvector  → semantic long-term memory (embeddings, durable)
  Supabase Postgres  → task state, tool call logs, HITL audit trail

Observability:
  OpenTelemetry spans (llm_call, tool.*, agent_task) → OTLP collector / Jaeger
```

---

## Tech Stack

| Component | Technology | Why |
|---|---|---|
| Orchestration | LangGraph | State machine with conditional edges, clean retry/escalation routing |
| LLM | OpenAI GPT-4o / GPT-4o-mini | Best reasoning for planning; mini for fast review |
| Tools | Custom registry + MCP + DuckDuckGo/Tavily | Rate-limited, agent-permissioned, fully logged |
| Tool interop | Model Context Protocol (stdio) | MCP server tools register alongside custom ones, indistinguishable to agents |
| Working Memory | Redis | Fast per-task ephemeral state shared across agents |
| Long-Term Memory | Supabase pgvector | Semantic vector search — system learns from past tasks |
| Persistence | Supabase (PostgreSQL) | Tasks, tool logs, HITL events survive restarts |
| Tracing | OpenTelemetry (+ Jaeger) | Standards-based spans over LLM calls, tool calls, and full task runs |
| Human Review | Streamlit | Real-time escalation queue with approve/reject/modify |
| API | FastAPI | Async task submission, polling, HITL resolution |
| Containers | Docker Compose | One-command full stack |

---

## Quickstart

### Prerequisites
- Docker Desktop
- OpenAI API key
- Supabase project (free tier)

### 1. Clone and configure
```bash
git clone https://github.com/Murali-Sai/Agent-Orchestration-System-with-Tool-Use-Memory-and-Human-in-the-Loop.git
cd Agent-Orchestration-System-with-Tool-Use-Memory-and-Human-in-the-Loop
cp .env.example .env
# Edit .env — add OPENAI_API_KEY (and optionally SUPABASE_URL + SUPABASE_ANON_KEY)
```

### 2. Set up Supabase
1. Create a free project at [supabase.com](https://supabase.com)
2. Run `db/schema.sql` in the Supabase SQL Editor
3. Run the RLS policies (see `db/schema.sql` comments)
4. Copy your Project URL and anon key into `.env`

`db/schema.sql` is safe to re-run on an existing database — it adds new columns
and replaces functions in place, so applying schema updates means running the
same file again.

### 3. Start the system
```bash
docker-compose up --build
```

| Service | URL |
|---|---|
| Streamlit UI | http://localhost:8501 |
| FastAPI | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Flower (Celery) | http://localhost:5555 |
| Jaeger (traces) | http://localhost:16686 |

---

## Quick Start — Try It Now

### Option 1: Automated demo script
```bash
python demo.py
```
Submits a showcase task, streams live progress, and prints a formatted summary.

### Option 2: cURL
```bash
# Submit a task
curl -s -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"request": "Research the top 3 AI agent frameworks and write a comparison brief.", "user_id": "demo"}' \
  | jq .

# Returns: {"task_id": "abc123", "status": "started"}

# Poll for status (replace abc123 with your task_id)
curl -s http://localhost:8000/tasks/abc123 | jq '{status, reviewer_score, cost_usd, total_tokens}'

# Get the full trace
curl -s http://localhost:8000/tasks/abc123/trace | jq '.trace[] | {agent, action}'

# Get step-through checkpoints
curl -s http://localhost:8000/tasks/abc123/checkpoints | jq '.checkpoints[] | {step, label, agent}'

# View aggregate analytics
curl -s http://localhost:8000/stats/aggregate | jq .
```

### Option 3: Python
```python
import requests, time

# Submit
r = requests.post("http://localhost:8000/tasks", json={
    "request": "Analyse the pros and cons of microservices vs monolith for a startup.",
    "user_id": "demo"
})
task_id = r.json()["task_id"]

# Poll until done
while True:
    state = requests.get(f"http://localhost:8000/tasks/{task_id}").json()
    if state["status"] in ("done", "failed", "escalated"):
        break
    time.sleep(3)

print(state["final_output"])
print(f"Cost: ${state['cost_usd']:.4f}  Score: {state['reviewer_score']:.2f}")
```

---

## Deploy to the Cloud (Render)

The repo ships a [`render.yaml`](render.yaml) Blueprint that provisions the whole
stack on [Render](https://render.com) in one click — no servers to manage.

**What it creates** (all on Render's free tier):

| Resource | Type | Notes |
|---|---|---|
| `aos-api` | Docker web service | FastAPI backend, health-checked at `/health` |
| `aos-ui` | Docker web service | Streamlit UI, auto-wired to the API |
| `aos-redis` | Key Value (Redis) | Working memory + HITL queue |

**Steps**

1. Push this repo to your GitHub account (already done if you cloned it there).
2. In Render: **New → Blueprint**, then select this repository. Render reads
   `render.yaml` and previews the three resources.
3. Set the one required secret when prompted: **`OPENAI_API_KEY`**.
   (Optional: `ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, `SUPABASE_URL`,
   `SUPABASE_ANON_KEY`.)
4. Click **Apply**. First build takes ~5–10 min. When live, open the `aos-ui`
   URL — it auto-connects to the API.

**Free-tier trade-offs** (fine for a demo, documented in `render.yaml`):
- Services spin down after 15 min idle (~1 min cold start on next request).
- Redis working memory is **ephemeral** — it resets on restart, since free
  instances have no persistent disk. Long-term memory is not affected: it lives
  in Supabase pgvector and survives restarts and redeploys, as do task state,
  tool logs, and the HITL audit trail.
- Celery/Flower are omitted (no free background workers); the API runs tasks in
  in-process threads automatically. Add a paid Background Worker to enable Celery.

---

## Key Features

### Multi-Agent Hierarchy
Three-layer agent design: Supervisor plans, Specialists execute, Reviewer validates. Each agent has a distinct role and prompt. The Supervisor synthesizes specialist outputs into a final answer.

### Tool Registry
All tools are registered with name, description, per-agent permissions, and rate limits. Every invocation is logged with inputs, outputs, latency, and success/failure — persisted to Supabase.

| Tool | Agents | Description |
|---|---|---|
| `web_search` | research, supervisor | Tavily / DuckDuckGo search |
| `execute_python` | code, analysis | Sandboxed Python execution |
| `read_file` / `write_file` | all / writing, code | Workspace-sandboxed file I/O |
| `db_query` | analysis, research, code | Read-only SQL against the agent SQLite DB |
| `db_list_tables` | all | List available database tables |
| `http_call` | research, code, analysis | Generic HTTP/REST API calls (SSRF-protected) |
| `mcp_workspace_*` | research, analysis, writing, code | Tools discovered from an MCP server — see below |

### Two-Tier Memory
- **Working memory (Redis)**: Per-task shared state for live execution progress
- **Long-term memory (Supabase pgvector)**: Embedded task summaries queried at planning time — the system references past approaches before creating a new plan

Long-term memory is actively maintained rather than write-only:
- **Composite retrieval** ranks by `cosine relevance × importance × recency`, with importance decaying on a 30-day half-life
- **Frequency-aware importance** — every memory surfaced to an agent increments an access counter, and often-retrieved memories earn a log-scaled importance boost (capped, so one popular memory can't crowd out the rest)
- **Consolidation** clusters near-duplicate embeddings by cosine similarity, keeps the highest-importance member, and bumps its score for having been independently corroborated

### Human-in-the-Loop (HITL)
Four escalation levels: Notify → Approve Action → Approve Plan → Take Over. Triggers automatically on low confidence, repeated failures, sensitive operations, or low review scores. The approval queue survives API restarts via Supabase.

Escalation is a last resort, not a first response. When the reviewer rejects an output, the graph first routes back to the **specialists** — not to re-synthesis — with the reviewer's feedback injected into each subtask prompt, so the second attempt has something new to work with. Only if that pass also scores below threshold does a human get pulled in. This bounds the retry at one pass: no loops, and no silently shipping an output the reviewer already failed.

### Full Observability
Every agent decision, tool call, and routing choice is recorded in an append-only trace. The Streamlit Trace Explorer visualizes the full decision tree. Token usage and costs tracked per task.

Underneath that timeline, the same work is emitted as **OpenTelemetry spans** — `agent_task` at the root, with `llm_call` (model, provider, token counts, cost) and `tool.*` (agent, success, latency, outcome) nested beneath it. Export is opt-in, so nothing is written unless you ask for it:

| Setting | Effect |
|---|---|
| *(unset)* | Spans are created and dropped — no output, negligible cost |
| `OTEL_CONSOLE_EXPORT=true` | Spans printed to stdout |
| `OTEL_EXPORTER_OTLP_ENDPOINT=host:4317` | Spans shipped to any OTLP collector |

`docker compose up` starts Jaeger wired to the API and workers — run a task, then open **http://localhost:16686** for a flame graph of the whole run.

### Tool Framework: Custom + MCP
The registry holds hand-written tools and **Model Context Protocol** tools side by side. MCP servers are discovered over stdio at startup and registered under an `mcp_<server>_<tool>` namespace, then go through the identical permission, rate-limit, tracing, and audit-log path — a specialist can't tell which kind it's calling.

The repo ships its own MCP server ([`tools/mcp_server.py`](tools/mcp_server.py), exposing `list_workspace`, `file_info`, `text_stats`) rather than depending on the Node-based reference servers, so no `npx` or Node runtime is needed in the container and discovery works on a cold free-tier boot. MCP tools honour the same workspace sandbox as the native file tools.

Disable with `ENABLE_MCP=false`, or point at other servers with `MCP_SERVERS=workspace,git`.

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

98 tests covering the graph's routing and rework loop, escalation triggers, the
tool registry and MCP bridge, memory scoring and consolidation, and the full
HTTP API. LLM calls are mocked, so the suite needs no API key beyond a
placeholder `OPENAI_API_KEY`. Long-term-memory integration tests skip
automatically unless `SUPABASE_URL` and a real `OPENAI_API_KEY` are set.

---

## Project Structure

```
├── agents/          # Supervisor, Specialist, Reviewer agents
├── graph/           # LangGraph state machine (state.py + workflow.py)
├── tools/           # Tool registry + web_search, code_executor, file_tools, MCP bridge
├── memory/          # Working memory (Redis) + Long-term memory (Supabase pgvector)
├── hitl/            # Escalation triggers + approval queue
├── db/              # Supabase client, CRUD, schema
├── api/             # FastAPI backend
├── ui/              # Streamlit frontend
├── config/          # Settings + logging
├── tests/           # Test suite
└── docker-compose.yml
```
