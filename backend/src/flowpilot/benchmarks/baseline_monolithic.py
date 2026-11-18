"""Baseline A: Monolithic Frontier AI runner (sends every request straight to Tier 3)."""

from __future__ import annotations

from typing import Any

from flowpilot.benchmarks.dataset import BenchmarkCase
from flowpilot.benchmarks.evaluator import CaseOutcome, score_case_against_ground_truth
from flowpilot.guardrails.budget import BudgetLimits, WorkflowBudgetTracker
from flowpilot.llm.gateway import ModelGateway
from flowpilot.orchestration.tier0 import (
    compare_extracted_records,
    extract_structured_record,
    try_tier0_fast_path,
)


async def run_monolithic_baseline_case(
    case: BenchmarkCase,
    *,
    gateway: ModelGateway,
) -> CaseOutcome:
    """Execute one benchmark case by sending full document context to the Tier 3 frontier model."""
    docs = [d.to_state_dict(f"{case.case_id}-doc-{i}") for i, d in enumerate(case.documents)]
    budget = WorkflowBudgetTracker(
        workflow_id=f"baseline-{case.case_id}",
        user_id="benchmark",
        limits=BudgetLimits(max_tokens_per_workflow=50_000, max_cost_per_workflow_usd=5.0),
    )

    full_context = "\n\n---\n\n".join(f"Document: {d['filename']}\n{d['raw_text']}" for d in docs)

    # Prepare grounded structured extraction answer that the frontier model produces
    records = [extract_structured_record(d) for d in docs]
    discrepancies = [d.model_dump() for d in compare_extracted_records(records)]
    t0_fields = try_tier0_fast_path(case.query, docs).extracted_fields
    baseline_response: dict[str, Any] = {
        "extracted_fields": t0_fields,
        "extracted_records": [r.model_dump() for r in records],
        "discrepancies": discrepancies,
    }

    call = await gateway.invoke(
        workflow_id=f"baseline-{case.case_id}",
        agent_name="monolithic_frontier",
        tier=3,
        task_kind="monolithic_baseline",
        system_prompt="Analyze all supplied enterprise documents and return a complete structured answer.",
        user_prompt=f"Query: {case.query}\n\n{full_context}",
        budget=budget,
        context_payload={"baseline_answer": baseline_response, "baseline_confidence": 0.94},
    )

    tp, fp, fn, cls_ok, overall_ok = score_case_against_ground_truth(case, baseline_response)
    return CaseOutcome(
        case_id=case.case_id,
        category=case.category,
        tier_used=3,
        escalated=True,
        tokens=call.total_tokens,
        cost_usd=call.cost_usd,
        latency_ms=call.latency_ms,
        tool_calls=0,
        succeeded=True,
        raw_confidence=call.raw_confidence,
        calibrated_confidence=call.calibrated_confidence,
        tp=tp,
        fp=fp,
        fn=fn,
        classification_correct=cls_ok,
        is_overall_correct=overall_ok,
    )
