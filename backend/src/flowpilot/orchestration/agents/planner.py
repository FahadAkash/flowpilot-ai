"""Planner Agent: creates minimal execution plan for Tier 2 multi-agent workflows.

Uses deterministic zero-token workflow templates for standard enterprise document
topologies (Invoice/PO/Policy 3-way match, Contract-vs-Contract diff) and reserves
LLM planning for novel or unstructured multi-document intents.
"""

from __future__ import annotations

import time
from typing import Any

from flowpilot.guardrails.budget import WorkflowBudgetTracker
from flowpilot.llm.gateway import ModelGateway
from flowpilot.orchestration.prompts import PLANNER_SYSTEM_PROMPT

KNOWN_TEMPLATE_INTENTS = {"multi_doc_comparison", "legal_reasoning"}


async def run_planner_agent(
    *,
    workflow_id: str,
    query: str,
    intent: str,
    documents: list[dict[str, Any]],
    gateway: ModelGateway,
    budget: WorkflowBudgetTracker,
) -> dict[str, Any]:
    """Produce a minimal ordered list of specialist steps required for this request."""
    budget.record_agent_call("planner")
    t0 = time.perf_counter()

    if intent in KNOWN_TEMPLATE_INTENTS:
        steps = ["retrieval", "extraction", "comparison", "validation"]
        return {
            "plan_steps": steps,
            "objective": f"Deterministic enterprise template plan for '{intent}'.",
            "model_log": None,
            "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            "raw_confidence": 0.96,
            "calibrated_confidence": 0.96,
        }

    doc_summary = [
        {
            "filename": d.get("filename"),
            "doc_type": d.get("doc_type"),
            "pages": d.get("page_count", 1),
        }
        for d in documents
    ]
    call = await gateway.invoke(
        workflow_id=workflow_id,
        agent_name="planner",
        tier=2,
        task_kind="plan",
        system_prompt=PLANNER_SYSTEM_PROMPT,
        user_prompt=f"Query: {query}\nIntent: {intent}\nDocuments: {doc_summary}",
        budget=budget,
        context_payload={"intent": intent, "documents": doc_summary},
    )
    raw_steps = call.structured_data.get("steps")
    steps = (
        [str(s) for s in raw_steps]
        if isinstance(raw_steps, list) and raw_steps
        else ["retrieval", "extraction", "comparison", "validation"]
    )
    return {
        "plan_steps": steps,
        "objective": str(call.structured_data.get("objective", "")),
        "model_log": call.invocation_record,
        "latency_ms": call.latency_ms,
        "raw_confidence": call.raw_confidence,
        "calibrated_confidence": call.calibrated_confidence,
    }
