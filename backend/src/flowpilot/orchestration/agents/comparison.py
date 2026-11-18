"""Comparison Agent: cross-document discrepancy and policy concern detection."""

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
