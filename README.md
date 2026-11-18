# FlowPilot AI — Tiered Multi-Agent Document Processing & Workflow Orchestrator

> **Core Proposition:** An enterprise AI orchestration platform that dynamically routes document workloads across **deterministic code (Tier 0)**, **lightweight AI (Tier 1)**, **LangGraph specialist multi-agent workflows (Tier 2)**, and **frontier model escalation (Tier 3)** while enforcing strict execution, latency, and cost guardrails.

---

## Why FlowPilot AI?

Traditional enterprise AI apps route every document request—from *"What is the invoice number?"* to *"Compare two conflicting contracts"*—directly to an expensive frontier LLM. That drives unnecessary token spend, high p95 latency, and unbounded tool-call loops.

FlowPilot AI solves this by making **routing itself** the architectural centerpiece:

| Tier | Execution Strategy | Cost | Latency | Example Requests |
|---|---|---:|---:|---|
| **Tier 0** | Deterministic Fast Path (Redis/Memory cache, regex, date/currency parsers, arithmetic & rule checks — **0 LLM tokens**) | $0.00 | ~2–10 ms | *"What is the invoice number?"*, *"Find the due date"*, *"Calculate total expenses"* |
| **Tier 1** | Lightweight AI (`gpt-4o-mini` / `gemini-2.5-flash-lite` / local `llama-3.1-8b`) | Very Low | ~60–120 ms | *"Classify whether this PDF is an invoice or contract"*, *"Extract structured invoice fields"* |
| **Tier 2** | LangGraph Planner + Specialist Agents (Retrieval via `pgvector`, Extraction, Comparison, Validation) | Medium | ~150–250 ms | *"Check whether Invoice.pdf follows PurchaseOrder.pdf and CompanyPolicy.pdf. Identify discrepancies."* |
| **Tier 3** | Frontier Model Escalation (`gpt-4o` / `claude-3-7-sonnet` / `gemini-2.5-pro`) — **max 1 escalation** | High | ~450 ms | *"Resolve conflicting indemnification, liability cap, and governing law clauses across Contract A & B"* |

---

## Verified Benchmark Results (Baseline A vs. Baseline B)

Evaluated on 16 identical multi-domain documents (UniDoc-Bench task categories: Invoices, Purchase Orders, Company Policies, Commercial Contracts, Financial Reports, and Healthcare Summaries) comparing **Baseline A (Monolithic Frontier)** against **Baseline B (FlowPilot Orchestrator)**:

| Metric | Baseline A (Monolithic Frontier) | Baseline B (FlowPilot Orchestrator) | Delta |
|---|---:|---:|---:|
| **Avg Tokens / Request** | 2,459.1 | **1,075.9** | **-56.2%** |
| **Avg Cost / Request (USD)** | $0.01409 | **$0.00171** | **-87.9%** |
| **p50 Latency** | 680.0 ms | **68.3 ms** | **-90.0%** |
| **p95 Latency** | 680.0 ms | **470.1 ms** | **-30.9%** |
| **Throughput** | 5.88 req/s | **32.20 req/s** | **5.48x** |
| **Field-Level F1** | 1.0000 | **1.0000** | +0.0000 |
| **Classification F1** | 1.0000 | **1.0000** | +0.0000 |
| **Escalation Rate** | 100.0% | **12.5%** | Selective |
| **Failure Rate** | 0.0% | **0.0%** | 100% reliable |
| **Calibration ECE** | 0.0782 | **0.0619** | Better calibrated |

Tier Routing Distribution across the 16-case suite: **6 Tier 0 · 4 Tier 1 · 4 Tier 2 · 2 Tier 3**.

Reproduce anytime with:
```bash
uv run --directory backend flowpilot-benchmark --output benchmark_report.md
```

---

## Architecture Highlights

### 1. Multi-Agent LangGraph Topology (8 Specialist Agents)
Built with `langgraph.graph.StateGraph`, typed raw state (`FlowPilotState`) with `operator.add` reducers, explicit conditional edges (`add_conditional_edges`), and `InMemorySaver` checkpointing keyed by `thread_id=workflow_id`:
- **Intent Router** · **Planner Agent** · **Retrieval Agent** · **Extraction Agent** · **Comparison Agent** · **Validation Agent** · **Reasoning Agent (Tier 3)** · **Response Agent**
- Agents are **skipped dynamically** whenever a lower tier satisfies the request (e.g., Tier 0 bypasses Planner, Retrieval, Comparison, and Reasoning).

### 2. Production Budget Guardrails & Reliability
Enforced across every LangGraph node, LLM call, and tool call:
- `max_steps` (default `12`), `max_agent_calls` (`15`), `max_tokens_per_workflow` (`10,000`), `timeout_seconds` (`60s`), `max_retries` (`2`), `max_tool_calls_per_agent` (`5`), `max_escalations` (`1`), configurable `confidence_threshold` (`0.80`)
- Global + per-user daily spend tracking, per-workflow cost tracking
- Per-provider/tier **Circuit Breakers** (`CLOSED -> OPEN -> HALF_OPEN`)
- **Idempotency** (`Idempotency-Key` header deduplication)
- Cooperative **Workflow Cancellation** (`POST /api/v1/workflows/{id}/cancel`)
- **Confidence Calibration** (ECE, reliability bins, linear calibration fitting, bidirectional threshold sweeps)

### 3. Database Architecture (12 Core Tables — PostgreSQL + `pgvector`)
Strictly separates workflow execution state (`workflows`, `workflow_steps`) from invocation & telemetry audit history (`model_invocations`, `tool_invocations`, `workflow_metrics`):
`users` · `documents` · `document_chunks` (`vector(384)`) · `workflows` · `workflow_steps` · `agents` · `model_registry` · `model_invocations` · `tool_invocations` · `budget_policies` · `workflow_metrics` · `evaluation_runs`

### 4. Tech Stack
- **Backend:** Python 3.12 (`uv`), FastAPI, LangGraph, Pydantic v2, SQLAlchemy 2.0 (async), Alembic, PyMuPDF (`pymupdf`), Celery
- **Data & Cache:** PostgreSQL 16 + `pgvector`, Redis 7
- **Observability:** Prometheus (`/metrics`) + provisioned Grafana dashboards + `structlog`
- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS v4, Recharts, Lucide
- **Deployment:** Docker & Docker Compose

---

## Quick Start

### Option A: Full Stack via Docker Compose
```bash
cp .env.example .env
docker compose up --build
```
- **Frontend Dashboard:** http://localhost:3000
- **Backend API & Swagger Docs:** http://localhost:8000/docs
- **Prometheus:** http://localhost:9090
- **Grafana:** http://localhost:3001 (`admin` / `flowpilot`)

### Option B: Local Development
```bash
# 1. Backend API (defaults to SQLite + MockProvider when no API keys are set)
cd backend
uv sync --extra dev
uv run uvicorn flowpilot.main:app --reload --port 8000

# 2. Frontend UI (new terminal)
cd frontend
npm install
npm run dev
```

### Switching to Live LLM Providers
Set `FLOWPILOT_LLM_PROVIDER` in `.env` to `openai`, `gemini`, `anthropic`, or `ollama` along with the corresponding API key (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, or `OLLAMA_BASE_URL`).

---

## Quality & Verification Commands
```bash
# Backend unit, integration & benchmark tests
uv run --directory backend pytest -v

# Linting, formatting & static typing
uv run --directory backend ruff check src tests
uv run --directory backend mypy src

# Frontend TypeScript check & production build
cd frontend && npm run build
```
