"""Comparative Benchmark Runner: Baseline A (Monolithic) vs Baseline B (FlowPilot Orchestrator)."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from flowpilot.benchmarks.baseline_monolithic import run_monolithic_baseline_case
from flowpilot.benchmarks.dataset import (
    BenchmarkCase,
    build_benchmark_suite,
    load_unidoc_bench_jsonl,
)
from flowpilot.benchmarks.evaluator import (
    AggregateBenchmarkMetrics,
    CaseOutcome,
    aggregate_outcomes,
    score_case_against_ground_truth,
)
from flowpilot.db.models import EvaluationRun
from flowpilot.guardrails.budget import BudgetLimits, WorkflowBudgetTracker
from flowpilot.llm.gateway import ModelGateway
from flowpilot.orchestration.graph import GraphRuntimeDeps, build_flowpilot_graph


async def run_flowpilot_benchmark_case(
    case: BenchmarkCase,
    *,
    gateway: ModelGateway,
) -> CaseOutcome:
    """Execute one benchmark case through the real FlowPilot Tier 0-3 LangGraph workflow."""
    docs = [d.to_state_dict(f"{case.case_id}-doc-{i}") for i, d in enumerate(case.documents)]
    budget = WorkflowBudgetTracker(
        workflow_id=f"bench-{case.case_id}",
        user_id="benchmark",
        limits=BudgetLimits(
            max_steps=12,
            max_agent_calls=15,
            max_tokens_per_workflow=10_000,
            max_escalations=1,
            timeout_seconds=180.0,
            confidence_threshold=0.80,
        ),
    )
    graph = build_flowpilot_graph(GraphRuntimeDeps(gateway=gateway, budget=budget, repo=None))
    state = await graph.ainvoke(
        {
            "workflow_id": f"bench-{case.case_id}",
            "user_id": "benchmark",
            "query": case.query,
            "documents": docs,
            "confidence_threshold": 0.80,
            "execution_trace": [],
            "model_logs": [],
            "tool_logs": [],
            "errors": [],
        },
        config={"configurable": {"thread_id": f"bench-{case.case_id}"}},
    )

    final_resp = dict(state.get("final_response") or {})
    trace = list(state.get("execution_trace") or [])
    latency_ms = round(sum(float(s.get("latency_ms", 0.0)) for s in trace), 2)
    tp, fp, fn, cls_ok, overall_ok = score_case_against_ground_truth(case, final_resp)

    return CaseOutcome(
        case_id=case.case_id,
        category=case.category,
        tier_used=int(state.get("current_tier", 0)),
        escalated=budget.escalations > 0,
        tokens=budget.tokens,
        cost_usd=round(budget.cost_usd, 7),
        latency_ms=max(1.5, latency_ms),
        tool_calls=budget.total_tool_calls,
        succeeded=bool(final_resp),
        raw_confidence=float(state.get("raw_confidence", 0.0)),
        calibrated_confidence=float(state.get("calibrated_confidence", 0.0)),
        tp=tp,
        fp=fp,
        fn=fn,
        classification_correct=cls_ok,
        is_overall_correct=overall_ok,
    )


def render_benchmark_markdown(
    baseline: AggregateBenchmarkMetrics,
    orchestrator: AggregateBenchmarkMetrics,
) -> str:
    """Render a side-by-side Markdown comparison report from persisted metrics."""
    token_red = (1.0 - orchestrator.avg_tokens / max(baseline.avg_tokens, 1.0)) * 100.0
    cost_red = (
        (1.0 - orchestrator.avg_cost_usd / baseline.avg_cost_usd) * 100.0
        if baseline.avg_cost_usd > 0
        else token_red
    )
    p95_red = (1.0 - orchestrator.p95_latency_ms / max(baseline.p95_latency_ms, 1.0)) * 100.0
    tput_mult = orchestrator.throughput_rps / max(baseline.throughput_rps, 0.01)

    lines = [
        "# FlowPilot AI — Baseline A vs. Baseline B Benchmark Report",
        "",
        f"**Dataset samples:** {orchestrator.sample_count} (identical documents & prompts for both runs)",
        "",
        "| Metric | Baseline A (Monolithic Frontier) | Baseline B (FlowPilot Orchestrator) | Delta |",
        "|---|---:|---:|---:|",
        f"| Avg Tokens / Request | {baseline.avg_tokens:,.1f} | {orchestrator.avg_tokens:,.1f} | **-{token_red:.1f}%** |",
        f"| Avg Cost / Request (USD) | ${baseline.avg_cost_usd:.5f} | ${orchestrator.avg_cost_usd:.5f} | **-{cost_red:.1f}%** |",
        f"| p50 Latency (ms) | {baseline.p50_latency_ms:.1f} ms | {orchestrator.p50_latency_ms:.1f} ms | -{(1 - orchestrator.p50_latency_ms / max(baseline.p50_latency_ms, 1)) * 100:.1f}% |",
        f"| p95 Latency (ms) | {baseline.p95_latency_ms:.1f} ms | {orchestrator.p95_latency_ms:.1f} ms | **-{p95_red:.1f}%** |",
        f"| Throughput (req/s) | {baseline.throughput_rps:.2f} | {orchestrator.throughput_rps:.2f} | **{tput_mult:.2f}x** |",
        f"| Field-Level F1 | {baseline.field_f1:.4f} | {orchestrator.field_f1:.4f} | {orchestrator.field_f1 - baseline.field_f1:+.4f} |",
        f"| Classification F1 | {baseline.classification_f1:.4f} | {orchestrator.classification_f1:.4f} | {orchestrator.classification_f1 - baseline.classification_f1:+.4f} |",
        f"| Escalation Rate | {baseline.escalation_rate * 100:.1f}% | {orchestrator.escalation_rate * 100:.1f}% | — |",
        f"| Avg Tool Calls / Request | {baseline.avg_tool_calls:.2f} | {orchestrator.avg_tool_calls:.2f} | — |",
        f"| Failure Rate | {baseline.failure_rate * 100:.1f}% | {orchestrator.failure_rate * 100:.1f}% | — |",
        f"| Calibration ECE | {baseline.ece_calibration_error:.4f} | {orchestrator.ece_calibration_error:.4f} | — |",
        "",
        "## FlowPilot Tier Routing Distribution",
        "",
        f"- **Tier 0 (Deterministic Fast Path):** {orchestrator.tier_distribution.get('tier_0', 0)} requests",
        f"- **Tier 1 (Lightweight AI):** {orchestrator.tier_distribution.get('tier_1', 0)} requests",
        f"- **Tier 2 (Planner + Specialist Agents):** {orchestrator.tier_distribution.get('tier_2', 0)} requests",
        f"- **Tier 3 (Frontier Escalation):** {orchestrator.tier_distribution.get('tier_3', 0)} requests",
    ]
    return "\n".join(lines)


async def run_comparative_benchmark(
    *,
    cases: list[BenchmarkCase] | None = None,
    dataset_name: str = "unidoc-bench-curated",
    run_name: str = "Baseline A vs FlowPilot Orchestrator",
    session: AsyncSession | None = None,
    gateway: ModelGateway | None = None,
) -> dict[str, Any]:
    """Run Baseline A and Baseline B on identical cases, optionally persisting to `evaluation_runs`."""
    eval_cases = cases or build_benchmark_suite(include_stress_cases=True)
    gw = gateway or ModelGateway()

    baseline_outcomes = [await run_monolithic_baseline_case(c, gateway=gw) for c in eval_cases]
    flowpilot_outcomes = [await run_flowpilot_benchmark_case(c, gateway=gw) for c in eval_cases]

    base_agg = aggregate_outcomes("baseline_monolithic", baseline_outcomes)
    fp_agg = aggregate_outcomes("flowpilot_orchestrator", flowpilot_outcomes)
    report_md = render_benchmark_markdown(base_agg, fp_agg)

    token_red = round((1.0 - fp_agg.avg_tokens / max(base_agg.avg_tokens, 1.0)) * 100.0, 2)
    cost_red = (
        round((1.0 - fp_agg.avg_cost_usd / base_agg.avg_cost_usd) * 100.0, 2)
        if base_agg.avg_cost_usd > 0
        else token_red
    )
    p95_red = round((1.0 - fp_agg.p95_latency_ms / max(base_agg.p95_latency_ms, 1.0)) * 100.0, 2)
    tput_mult = round(fp_agg.throughput_rps / max(base_agg.throughput_rps, 0.01), 2)
    f1_delta = round(fp_agg.field_f1 - base_agg.field_f1, 4)

    base_row: EvaluationRun | None = None
    fp_row: EvaluationRun | None = None
    if session is not None:
        base_row = _to_eval_run_orm(f"{run_name} [Baseline A]", dataset_name, base_agg)
        fp_row = _to_eval_run_orm(f"{run_name} [FlowPilot]", dataset_name, fp_agg)
        session.add(base_row)
        session.add(fp_row)
        await session.commit()
        await session.refresh(base_row)
        await session.refresh(fp_row)

    return {
        "baseline": base_agg,
        "flowpilot": fp_agg,
        "baseline_row": base_row,
        "flowpilot_row": fp_row,
        "token_reduction_pct": token_red,
        "cost_reduction_pct": cost_red,
        "p95_latency_reduction_pct": p95_red,
        "throughput_multiplier": tput_mult,
        "f1_delta": f1_delta,
        "calibration_bins": fp_agg.calibration_bins,
        "report_markdown": report_md,
    }


def _to_eval_run_orm(name: str, dataset_name: str, agg: AggregateBenchmarkMetrics) -> EvaluationRun:
    return EvaluationRun(
        name=name,
        dataset_name=dataset_name,
        mode=agg.mode,
        sample_count=agg.sample_count,
        avg_tokens=agg.avg_tokens,
        avg_cost_usd=agg.avg_cost_usd,
        p50_latency_ms=agg.p50_latency_ms,
        p95_latency_ms=agg.p95_latency_ms,
        throughput_rps=agg.throughput_rps,
        field_precision=agg.field_precision,
        field_recall=agg.field_recall,
        field_f1=agg.field_f1,
        classification_f1=agg.classification_f1,
        escalation_rate=agg.escalation_rate,
        avg_tool_calls=agg.avg_tool_calls,
        failure_rate=agg.failure_rate,
        ece_calibration_error=agg.ece_calibration_error,
        tier_distribution_json=agg.tier_distribution,
        details_json={"outcomes": agg.outcomes, "calibration_bins": agg.calibration_bins},
    )


def cli_main() -> None:
    parser = argparse.ArgumentParser(description="Run FlowPilot AI Baseline A vs B benchmark.")
    parser.add_argument(
        "--jsonl", type=Path, default=None, help="Optional external UniDoc-Bench JSONL file"
    )
    parser.add_argument("--output", type=Path, default=None, help="Optional Markdown output path")
    args = parser.parse_args()

    cases = load_unidoc_bench_jsonl(args.jsonl) if args.jsonl else build_benchmark_suite()
    result = asyncio.run(run_comparative_benchmark(cases=cases))
    print(result["report_markdown"])
    if args.output:
        args.output.write_text(result["report_markdown"], encoding="utf-8")


if __name__ == "__main__":
    cli_main()
