"""Response Agent: compiles the final grounded structured report and routing rationale."""

from __future__ import annotations

from typing import Any

from flowpilot.guardrails.budget import WorkflowBudgetTracker
from flowpilot.orchestration.prompts import COMPLIANCE_DISCLAIMER

ALL_SPECIALIST_AGENTS = [
    "intent_router",
    "planner",
    "retrieval",
    "extraction",
    "comparison",
    "validation",
    "reasoning",
    "response",
]


async def run_response_agent(
    *,
    state: dict[str, Any],
    budget: WorkflowBudgetTracker,
) -> dict[str, Any]:
    """Synthesize final executive summary, structured findings, citations, and skipped agents."""
    budget.record_agent_call("response")

    tier = int(state.get("current_tier", state.get("selected_tier", 0)))
    intent = str(state.get("intent", "unknown"))
    discrepancies: list[dict[str, Any]] = list(state.get("discrepancies") or [])
    extracted_records: list[dict[str, Any]] = list(state.get("extracted_records") or [])
    reasoning_out: dict[str, Any] = dict(state.get("reasoning_output") or {})
    tier0_out: dict[str, Any] = dict(state.get("tier0_output") or {})
    tier1_out: dict[str, Any] = dict(state.get("tier1_output") or {})
    validation: dict[str, Any] = dict(state.get("validation_report") or {})

    executed_agents = {step.get("agent_name") for step in state.get("execution_trace", [])}
    executed_agents.add("response")
    skipped_agents = [a for a in ALL_SPECIALIST_AGENTS if a not in executed_agents]

    citations: list[str] = []
    for c in tier0_out.get("citations", []):
        if c not in citations:
            citations.append(c)
    for r in extracted_records:
        for c in r.get("citations", []):
            if c not in citations:
                citations.append(c)
    for d in discrepancies:
        c = d.get("citation")
        if c and c not in citations:
            citations.append(c)

    if tier0_out.get("answer"):
        summary = str(tier0_out["answer"])
    elif tier1_out.get("answer") and not discrepancies and not reasoning_out:
        summary = str(tier1_out["answer"])
    elif discrepancies:
        high_cnt = sum(1 for d in discrepancies if d.get("severity") in {"high", "critical"})
        summary = (
            f"Completed Tier {tier} multi-document review across {len(extracted_records)} document(s). "
            f"Identified **{len(discrepancies)} potential discrepancy/concern item(s)** "
            f"({high_cnt} high/critical severity)."
        )
        if reasoning_out.get("executive_reasoning"):
            summary += f" {reasoning_out['executive_reasoning']}"
    else:
        summary = (
            f"Completed Tier {tier} analysis across {len(extracted_records) or len(state.get('documents', []))} "
            "document(s) with no discrepancies detected."
        )
        if reasoning_out.get("executive_reasoning"):
            summary += f" {reasoning_out['executive_reasoning']}"

    return {
        "summary": summary,
        "intent": intent,
        "selected_tier": int(state.get("selected_tier", 0)),
        "final_tier": tier,
        "routing_rationale": str(state.get("routing_rationale", "")),
        "extracted_fields": tier0_out.get("extracted_fields") or {},
        "extracted_records": extracted_records,
        "discrepancies": discrepancies,
        "frontier_reasoning": reasoning_out or None,
        "validation": validation,
        "citations": citations,
        "executed_agents": sorted(a for a in executed_agents if a),
        "skipped_agents": skipped_agents,
        "disclaimer": COMPLIANCE_DISCLAIMER if tier >= 2 or discrepancies else None,
    }
