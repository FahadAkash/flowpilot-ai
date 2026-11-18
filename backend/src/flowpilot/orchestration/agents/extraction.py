"""Extraction Agent: structured Pydantic field extraction across retrieved documents."""

from __future__ import annotations

import time
from typing import Any

from flowpilot.guardrails.budget import WorkflowBudgetTracker
from flowpilot.llm.gateway import ModelGateway
from flowpilot.orchestration.prompts import EXTRACTION_SYSTEM_PROMPT
from flowpilot.orchestration.tier0 import extract_structured_record


async def run_extraction_agent(
    *,
    workflow_id: str,
    query: str,
    documents: list[dict[str, Any]],
    retrieved_chunks: list[dict[str, Any]],
    gateway: ModelGateway,
    budget: WorkflowBudgetTracker,
    retry_feedback: str | None = None,
) -> dict[str, Any]:
    """Extract typed records for each document using deterministic grounding + Tier 2 SLM."""
    budget.record_agent_call("extraction")
    budget.record_tool_call("extraction", "structured_field_parser")

    t0 = time.perf_counter()
    records = [extract_structured_record(d).model_dump() for d in documents]
    tool_latency = round((time.perf_counter() - t0) * 1000.0, 2)
    tool_log = {
        "agent_name": "extraction",
        "tool_name": "structured_field_parser",
        "arguments_json": {"doc_count": len(documents), "is_retry": bool(retry_feedback)},
        "result_summary_json": {"records_extracted": len(records)},
        "latency_ms": tool_latency,
        "status": "success",
        "error_message": None,
    }

    chunk_excerpt = "\n".join(
        f"[{c['filename']} p.{c['page_number']}] {c['content'][:220]}" for c in retrieved_chunks[:3]
    )
    prompt = (
        f"Query: {query}\n"
        f"{f'Retry guidance: {retry_feedback}' if retry_feedback else ''}\n"
        f"Excerpts:\n{chunk_excerpt}"
    )

    populated = sum(
        1
        for r in records
        if r.get("document_number")
        or r.get("total_amount") is not None
        or r.get("policy_rules")
        or r.get("contract_clauses")
    )
    completeness = 0.80 + (0.14 * (populated / max(len(records), 1)))

    call = await gateway.invoke(
        workflow_id=workflow_id,
        agent_name="extraction",
        tier=2,
        task_kind="extract_structured",
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        user_prompt=prompt,
        budget=budget,
        context_payload={"pre_extracted": records, "completeness_score": completeness},
    )

    return {
        "extracted_records": records,
        "raw_confidence": call.raw_confidence,
        "calibrated_confidence": call.calibrated_confidence,
        "model_log": call.invocation_record,
        "tool_logs": [tool_log],
    }
