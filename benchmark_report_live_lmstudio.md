# FlowPilot AI — Baseline A vs. Baseline B Benchmark Report

**Dataset samples:** 16 (identical documents & prompts for both runs)

| Metric | Baseline A (Monolithic Frontier) | Baseline B (FlowPilot Orchestrator) | Delta |
|---|---:|---:|---:|
| Avg Tokens / Request | 692.9 | 400.5 | **-42.2%** |
| Avg Cost / Request (USD) | $0.00000 | $0.00000 | **-42.2%** |
| p50 Latency (ms) | 34545.6 ms | 21103.9 ms | -38.9% |
| p95 Latency (ms) | 39398.3 ms | 76646.4 ms | **--94.5%** |
| Throughput (req/s) | 0.12 | 0.18 | **1.50x** |
| Field-Level F1 | 1.0000 | 1.0000 | +0.0000 |
| Classification F1 | 1.0000 | 1.0000 | +0.0000 |
| Escalation Rate | 100.0% | 12.5% | — |
| Avg Tool Calls / Request | 0.00 | 1.50 | — |
| Failure Rate | 0.0% | 0.0% | — |
| Calibration ECE | 0.1240 | 0.0893 | — |

## FlowPilot Tier Routing Distribution

- **Tier 0 (Deterministic Fast Path):** 6 requests
- **Tier 1 (Lightweight AI):** 4 requests
- **Tier 2 (Planner + Specialist Agents):** 4 requests
- **Tier 3 (Frontier Escalation):** 2 requests