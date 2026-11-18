"""Reasoning Agent: Tier 3 Frontier Model Escalation (strictly gated)."""

from __future__ import annotations

from typing import Any

from flowpilot.guardrails.budget import WorkflowBudgetTracker
from flowpilot.llm.gateway import ModelGateway
from flowpilot.observability.metrics import ESCALATIONS_TOTAL
from flowpilot.orchestration.prompts import REASONING_TIER3_SYSTEM_PROMPT


async def run_reasoning_agent_tier3(
    *,
    workflow_id: str,
    query: str,
    from_tier: int,
    escalation_reason: str,
    extracted_records: list[dict[str, Any]],
    discrepancies: list[dict[str, Any]],
    gateway: ModelGateway,
    budget: WorkflowBudgetTracker,
) -> dict[str, Any]:
    """Escalate to Tier 3 frontier model for ambiguous conflicts or low-confidence cases."""
    budget.record_escalation(escalation_reason)
    budget.record_agent_call("reasoning")
    ESCALATIONS_TOTAL.labels(
        from_tier=str(from_tier),
        to_tier="3",
        reason=escalation_reason[:48],
    ).inc()

    compact_records = [
        {k: v for k, v in r.items() if v not in (None, "", [], {}) and k != "citations"}
        for r in extracted_records
    ]
    compact_diffs = [
        {
            "code": d.get("code"),
            "field": d.get("field"),
            "expected": d.get("expected"),
            "actual": d.get("actual"),
        }
        for d in discrepancies
    ]
    prompt = (
        f"Escalation reason: {escalation_reason}\n"
        f"User Query: {query}\n"
        f"Compact Records: {compact_records}\n"
        f"Conflicts: {compact_diffs}"
    )

    call = await gateway.invoke(
        workflow_id=workflow_id,
        agent_name="reasoning",
        tier=3,
        task_kind="frontier_reasoning",
        system_prompt=REASONING_TIER3_SYSTEM_PROMPT,
        user_prompt=prompt,
        budget=budget,
        context_payload={"query": query, "discrepancies": discrepancies},
    )

    return {
        "reasoning_output": call.structured_data,
        "raw_confidence": call.raw_confidence,
        "calibrated_confidence": call.calibrated_confidence,
        "model_log": call.invocation_record,
    }
