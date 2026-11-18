# FlowPilot AI — Baseline A vs. Baseline B Benchmark Report

**Dataset samples:** 16 (identical documents & prompts for both runs)

| Metric | Baseline A (Monolithic Frontier) | Baseline B (FlowPilot Orchestrator) | Delta |
|---|---:|---:|---:|
| Avg Tokens / Request | 2,459.1 | 1,075.9 | **-56.2%** |
| Avg Cost / Request (USD) | $0.01409 | $0.00171 | **-87.9%** |
| p50 Latency (ms) | 680.0 ms | 63.7 ms | -90.6% |
| p95 Latency (ms) | 680.0 ms | 470.0 ms | **-30.9%** |
| Throughput (req/s) | 5.88 | 32.45 | **5.52x** |
| Field-Level F1 | 1.0000 | 1.0000 | +0.0000 |
| Classification F1 | 1.0000 | 1.0000 | +0.0000 |
| Escalation Rate | 100.0% | 12.5% | — |
| Avg Tool Calls / Request | 0.00 | 1.50 | — |
| Failure Rate | 0.0% | 0.0% | — |
| Calibration ECE | 0.0782 | 0.0619 | — |

## FlowPilot Tier Routing Distribution

- **Tier 0 (Deterministic Fast Path):** 6 requests
- **Tier 1 (Lightweight AI):** 4 requests
- **Tier 2 (Planner + Specialist Agents):** 4 requests
- **Tier 3 (Frontier Escalation):** 2 requests