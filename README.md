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

Evaluated on **16 identical multi-domain documents** (UniDoc-Bench task categories: Invoices, Purchase Orders, Company Policies, Commercial Contracts, Financial Reports, and Healthcare Summaries) comparing **Baseline A (Monolithic Frontier)** against **Baseline B (FlowPilot Orchestrator)**.

### 1. Live Hardware Benchmark — Local LM Studio (`google/gemma-4-12b-qat`) + PostgreSQL 17 (`pgvector 0.8.7`, 768-dim Nomic) + Redis 7

Measured end-to-end on real local GPU inference (`$0.00` API cost) with remote PostgreSQL 17 `pgvector` and Redis 7:

| Metric | Baseline A (Monolithic `gemma-4-12b-qat`) | Baseline B (FlowPilot Orchestrator) | Delta |
|---|---:|---:|---:|
| **Avg Tokens / Request** | 692.9 | **400.5** | **-42.2%** |
| **p50 Latency** | 34,545.6 ms (34.5s) | **21,103.9 ms (21.1s)** | **-38.9%** |
| **Tier 0 Fast-Path Latency** | 11,545–33,259 ms | **1.5–65.5 ms** (`2.7 ms` Redis cache hit) | **>500x faster** |
| **Throughput** | 0.12 req/s | **0.18 req/s** | **1.50x** |
| **Field-Level F1** | 1.0000 | **1.0000** | +0.0000 |
| **Classification F1** | 1.0000 | **1.0000** | +0.0000 |
| **Escalation Rate** | 100.0% | **12.5%** | Selective |
| **Failure Rate** | 0.0% | **0.0%** | 100% reliable |
| **Calibration ECE** | 0.1240 | **0.0893** | **-28.0% ECE** |

### 2. Heterogeneous Multi-Tier Cloud Pricing Benchmark (`gpt-4o-mini` Tier 1/2 + `gpt-4o` Tier 3)

| Metric | Baseline A (Monolithic Frontier) | Baseline B (FlowPilot Orchestrator) | Delta |
|---|---:|---:|---:|
| **Avg Tokens / Request** | 2,459.1 | **1,075.9** | **-56.2%** |
| **Avg Cost / Request (USD)** | $0.01409 | **$0.00171** | **-87.9%** |
| **p50 Latency** | 680.0 ms | **63.7 ms** | **-90.6%** |
| **p95 Latency** | 680.0 ms | **470.1 ms** | **-30.9%** |
| **Throughput** | 5.88 req/s | **32.45 req/s** | **5.52x** |
| **Field-Level F1** | 1.0000 | **1.0000** | +0.0000 |
| **Classification F1** | 1.0000 | **1.0000** | +0.0000 |
| **Escalation Rate** | 100.0% | **12.5%** | Selective |
| **Failure Rate** | 0.0% | **0.0%** | 100% reliable |

Tier Routing Distribution across both 16-case runs: **6 Tier 0 · 4 Tier 1 · 4 Tier 2 · 2 Tier 3**.

### 3. Non-LLM Engineering Subsystems & Infrastructure Benchmark

To eliminate local LLM inference variance and independently evaluate all backend, vector, caching, and orchestration pipelines, we benchmarked the non-LLM engineering subsystems directly against live infrastructure:
- **PostgreSQL 17.12 + `pgvector 0.8.7`** on `192.168.0.113:5433/flowpilot`
- **Redis 7.4.11** on `192.168.0.113:6379/3`
- **Neural Embeddings** (`text-embedding-nomic-embed-text-v1.5@q8_0`, 768-dim)

| Subsystem | Backing Engine | Tested Operations | p50 Latency | p95 Latency | p99 Latency | Throughput | Zero-LLM Cost |
|---|---|---:|---:|---:|---:|---:|---:|
| **1. Tier 0 Deterministic Path** | Compiled Regex + Math + Date Parsers | 600 ops | **0.15 ms** | **0.41 ms** | 0.68 ms | **4,816.2 ops/s** | $0.00 / 0 tokens |
| **2. Production Guardrails Engine** | 8 Guards + CircuitBreaker + Cancellation + ContextLimiter | 1,000 ops | **0.01 ms** | **0.95 ms** | 1.27 ms | **5,677.0 ops/s** | $0.00 / 0 tokens |
| **3. 3-Way Diff & Pydantic v2 Validation** | Deterministic Rules + Pydantic v2 Schema | 150 ops | **1.02 ms** | **1.99 ms** | 3.49 ms | **812.1 ops/s** | $0.00 / 0 tokens |
| **4. PDF Ingestion & Chunking** | PyMuPDF (`pymupdf`) Structure-Aware Chunker | 50 docs | **2.49 ms** | **5.27 ms** | 45.47 ms | **282.3 docs/s** | $0.00 / 0 tokens |
| **5. Remote Redis 7 Cache** | Redis 7 Network SET + GET Round-Trip Pair | 150 ops | **4.44 ms** | **7.75 ms** | 10.46 ms | **197.9 ops/s** | $0.00 / 0 tokens |
| **6. FastAPI Concurrent HTTP Throughput** | ASGI (10x concurrency, real DB + Redis mix) | 60 requests | **90.92 ms** | **305.32 ms** | 344.06 ms | **78.2 req/s** | 0 errors |
| **7. LangGraph + PostgreSQL 17 Persistence** | `StateGraph` Transitions + 5-Table Audit Writes | 20 workflows | **260.05 ms** | **757.26 ms** | 783.59 ms | **2.5 wf/s** | Full audit persistence |
| **8. 768-dim Neural Embeddings** | Nomic Embed v1.5 (Local GPU API) | 25 chunks | **485.52 ms** | **520.42 ms** | 567.73 ms | **2.1 chunks/s** | $0.00 / 0 tokens |
| **9. pgvector Hybrid Retrieval** | PostgreSQL 17 `pgvector` Cosine + Lexical Rerank | 40 queries | **510.32 ms** | **614.93 ms** | 622.65 ms | **1.9 queries/s** | top_k=5 reranked |

Reproduce anytime with:
```bash
# Run full benchmark (Baseline A vs Baseline B)
uv run --directory backend flowpilot-benchmark --output benchmark_report.md

# Run live non-LLM infrastructure benchmark
uv run --directory backend python -m flowpilot.benchmarks.infra_benchmark --output benchmark_report_infra.md
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
