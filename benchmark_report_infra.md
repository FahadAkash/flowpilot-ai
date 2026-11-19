# FlowPilot AI — Systems & Infrastructure Benchmark Report (Non-LLM)

- **PostgreSQL + pgvector:** `192.168.0.113:5433/flowpilot`
- **Redis Cache:** `192.168.0.113:6379/3`
- **Embedding Model:** `text-embedding-nomic-embed-text-v1.5@q8_0` (`768` dims)
- **Scope:** Pure backend, database, vector search, cache, PDF parsing, deterministic routing, guardrails, and LangGraph state orchestration (excludes local LLM generation latency).

| Subsystem | Backing Engine | Ops | p50 (ms) | p95 (ms) | p99 (ms) | Throughput (ops/s) | Notes |
|---|---|---:|---:|---:|---:|---:|---|
| 1. PDF Parse + Chunk | PyMuPDF (pymupdf) | 50 | **2.49** | **5.27** | 45.47 | **282.3** | 5 real enterprise PDFs (1 chunks/doc) |
| 2. 768-dim Neural Embeddings | LM Studio (text-embedding-nomic-embed-text-v1.5@q8_0) | 25 | **485.52** | **520.42** | 567.73 | **2.1** | dim=768 (warm=768) |
| 3. pgvector Hybrid Retrieval | PostgreSQL 17 (192.168.0.113:5433/flowpilot) | 40 | **510.32** | **614.93** | 622.65 | **1.9** | 768-dim cosine + lexical rerank (top_k=5) |
| 4. Redis 7 Cache (SET+GET) | Redis 7 (192.168.0.113:6379/3) | 150 | **4.44** | **7.75** | 10.46 | **197.9** | Remote network SET + GET round-trip pair |
| 5. Tier 0 Deterministic Path | Zero-LLM Regex + Math | 600 | **0.15** | **0.41** | 0.68 | **4,816.2** | 100% handled (600/600), 0 LLM tokens |
| 6. 3-Way Diff + Pydantic v2 | Deterministic Rules + Schema | 150 | **1.02** | **1.99** | 3.49 | **812.1** | Invoice/PO/Policy + 2-Contract diff (12 findings/run) |
| 7. Production Guardrails | Budget + CB + Cancel + Context | 1000 | **0.01** | **0.95** | 1.27 | **5,677.0** | All 8 guardrails + circuit breaker + token limiter |
| 8. LangGraph + Postgres E2E | StateGraph + 5-Table Write | 20 | **260.05** | **757.26** | 783.59 | **2.5** | Full Tier 0-3 graph + steps/models/tools/metrics DB writes |
| 9. FastAPI Concurrent HTTP | ASGI (10x concurrency) | 60 | **90.92** | **305.32** | 344.06 | **78.2** | Mix: /health, Tier 0 Cache, /analytics, /metrics (errors=0) |

## PostgreSQL 17 Table Verification

- `users`: **1** row(s)
- `documents`: **25** row(s)
- `document_chunks`: **25** row(s)
- `workflows`: **55** row(s)
- `workflow_steps`: **203** row(s)
- `agents`: **8** row(s)
- `model_registry`: **8** row(s)
- `model_invocations`: **25** row(s)
- `tool_invocations`: **54** row(s)
- `budget_policies`: **3** row(s)
- `workflow_metrics`: **54** row(s)
- `evaluation_runs`: **4** row(s)