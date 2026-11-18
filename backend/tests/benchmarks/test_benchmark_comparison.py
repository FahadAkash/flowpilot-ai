"""Benchmark validation tests: proves Baseline B outperforms Baseline A while keeping high F1."""

from __future__ import annotations

import pytest
from flowpilot.benchmarks.runner import run_comparative_benchmark
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_baseline_a_vs_flowpilot_benchmark_proves_efficiency_and_quality() -> None:
    res = await run_comparative_benchmark()
    base = res["baseline"]
    fp = res["flowpilot"]

    assert fp.sample_count == base.sample_count == 16
    assert fp.failure_rate == 0.0
    assert fp.field_f1 >= 0.92
    assert fp.classification_f1 >= 0.92

    # Efficiency proof against monolithic frontier baseline
    assert res["token_reduction_pct"] >= 50.0
    assert res["cost_reduction_pct"] >= 75.0
    assert res["p95_latency_reduction_pct"] >= 20.0
    assert res["throughput_multiplier"] >= 2.5

    # Router actually uses all four tiers appropriately (not monolithic)
    assert fp.tier_distribution["tier_0"] >= 5
    assert fp.tier_distribution["tier_1"] >= 3
    assert fp.tier_distribution["tier_2"] >= 3
    assert fp.tier_distribution["tier_3"] >= 1
    assert fp.escalation_rate < 0.25


@pytest.mark.asyncio
async def test_benchmark_api_persists_evaluation_runs(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/benchmarks/run",
        json={"name": "CI Verification Run", "dataset_name": "unidoc-bench-curated"},
    )
    assert resp.status_code == 200
    comp = resp.json()
    assert comp["token_reduction_pct"] > 50.0
    assert comp["cost_reduction_pct"] > 75.0
    assert "FlowPilot AI" in comp["report_markdown"]

    runs = (await client.get("/api/v1/benchmarks/runs")).json()
    assert len(runs) == 2

    latest = await client.get("/api/v1/benchmarks/latest-comparison")
    assert latest.status_code == 200
    assert latest.json()["flowpilot_orchestrator"]["field_f1"] >= 0.92
