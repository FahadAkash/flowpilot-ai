"""Comparison Agent: deterministic-first cross-document discrepancy detection.

Avoids wasting intermediate LLM calls when:
1. Ambiguous legal conflicts are already flagged for Tier 3 escalation (hands compact diff
   straight to Tier 3 so only ONE frontier call runs instead of stacking Tier 2 + Tier 3).
2. A clean 0-discrepancy compliance check passes deterministically with zero variance.
"""

from __future__ import annotations

import time
from typing import Any

from flowpilot.guardrails.budget import WorkflowBudgetTracker
from flowpilot.llm.gateway import ModelGateway
from flowpilot.orchestration.prompts import COMPARISON_SYSTEM_PROMPT
from flowpilot.orchestration.tier0 import compare_extracted_records
from flowpilot.schemas.workflows import ExtractedDocumentRecord


async def run_comparison_agent(
    *,
    workflow_id: str,
    query: str,
    extracted_records: list[dict[str, Any]],
    gateway: ModelGateway,
    budget: WorkflowBudgetTracker,
) -> dict[str, Any]:
    """Compare extracted records across invoices, POs, policies, and contracts."""
    budget.record_agent_call("comparison")
    budget.record_tool_call("comparison", "cross_document_diff_engine")

    t0 = time.perf_counter()
    typed_records = [ExtractedDocumentRecord.model_validate(r) for r in extracted_records]
    discrepancies = [d.model_dump() for d in compare_extracted_records(typed_records)]
    tool_latency = round((time.perf_counter() - t0) * 1000.0, 2)

    has_ambiguous = any(d.get("requires_frontier_reasoning") for d in discrepancies)

    tool_log = {
        "agent_name": "comparison",
        "tool_name": "cross_document_diff_engine",
        "arguments_json": {"records_compared": len(typed_records)},
        "result_summary_json": {
            "discrepancies_found": len(discrepancies),
            "ambiguous_conflicts": sum(
                1 for d in discrepancies if d.get("requires_frontier_reasoning")
            ),
        },
        "latency_ms": tool_latency,
        "status": "success",
        "error_message": None,
    }

    # Fast handoff to Tier 3 when ambiguous legal/contractual conflicts are already identified
    if has_ambiguous:
        return {
            "discrepancies": discrepancies,
            "raw_confidence": 0.68,
            "calibrated_confidence": 0.68,
            "model_log": None,
            "tool_logs": [tool_log],
        }

    # Zero-LLM pass when deterministic rules verified 0 discrepancies across structured records
    if not discrepancies:
        return {
            "discrepancies": [],
            "raw_confidence": 0.95,
            "calibrated_confidence": 0.95,
            "model_log": None,
            "tool_logs": [tool_log],
        }

    compact_diffs = [
        {"code": d["code"], "field": d["field"], "expected": d["expected"], "actual": d["actual"]}
        for d in discrepancies
    ]
    call = await gateway.invoke(
        workflow_id=workflow_id,
        agent_name="comparison",
        tier=2,
        task_kind="compare_documents",
        system_prompt=COMPARISON_SYSTEM_PROMPT,
        user_prompt=f"Query: {query}\nRecords: {len(typed_records)}\nCompact diffs: {compact_diffs}",
        budget=budget,
        context_payload={"detected_discrepancies": discrepancies},
    )

    return {
        "discrepancies": discrepancies,
        "raw_confidence": call.raw_confidence,
        "calibrated_confidence": call.calibrated_confidence,
        "model_log": call.invocation_record,
        "tool_logs": [tool_log],
    }
