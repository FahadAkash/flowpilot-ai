"""Intent Router: selects the cheapest capable tier (Tier 0 -> 1 -> 2 -> 3)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from flowpilot.guardrails.budget import WorkflowBudgetTracker
from flowpilot.llm.gateway import ModelGateway
from flowpilot.orchestration.prompts import INTENT_ROUTER_SYSTEM_PROMPT
from flowpilot.orchestration.tier0 import try_tier0_fast_path


@dataclass(slots=True)
class RoutingDecision:
    intent: str
    selected_tier: int
    rationale: str
    raw_confidence: float
    calibrated_confidence: float
    tier0_preview: dict[str, Any] | None = None
    model_log: dict[str, Any] | None = None
    latency_ms: float = 0.0


async def route_intent(
    *,
    workflow_id: str,
    query: str,
    documents: list[dict[str, Any]],
    gateway: ModelGateway,
    budget: WorkflowBudgetTracker,
    force_tier: int | None = None,
) -> RoutingDecision:
    """Decide whether a task needs Tier 0 deterministic code, Tier 1 SLM, Tier 2 multi-agent, or Tier 3."""
    t0 = time.perf_counter()
    q_low = query.lower().strip()
    doc_count = len(documents)

    if force_tier is not None:
        return RoutingDecision(
            intent="forced_tier_execution",
            selected_tier=force_tier,
            rationale=f"Explicitly routed to Tier {force_tier} via request override.",
            raw_confidence=1.0,
            calibrated_confidence=1.0,
            latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )

    # Step 1: Attempt zero-LLM Tier 0 deterministic resolution first!
    t0_probe = try_tier0_fast_path(query, documents)
    if t0_probe.handled:
        return RoutingDecision(
            intent=t0_probe.intent,
            selected_tier=0,
            rationale=(
                f"Matched deterministic rule '{t0_probe.matched_rule}' with zero LLM tokens required."
            ),
            raw_confidence=1.0,
            calibrated_confidence=1.0,
            tier0_preview={
                "answer": t0_probe.answer,
                "extracted_fields": t0_probe.extracted_fields,
                "citations": t0_probe.citations,
                "matched_rule": t0_probe.matched_rule,
            },
            latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )

    # Step 2: Fast deterministic structural signals for obvious Tier 2 multi-doc workflows
    legal_signals = (
        "indemn",
        "conflict",
        "ambiguous",
        "governing law",
        "liability cap",
        "legal clause",
    )
    multi_doc_signals = (
        "compare",
        "discrepanc",
        "follows our",
        "purchase order",
        "company policy",
        "compliance",
        "match",
        "3-way",
        "three-way",
        "audit",
    )
    tier1_signals = (
        "classify",
        "what type of document",
        "is this an invoice",
        "document type",
        "extract all",
        "extract entities",
        "extract vendor",
        "summarize",
        "key points",
    )

    if any(sig in q_low for sig in legal_signals) and doc_count >= 1:
        return RoutingDecision(
            intent="legal_reasoning",
            selected_tier=2,
            rationale=(
                "Detected complex legal/contract conflict indicators; routing to Tier 2 "
                "Planner + Specialist Agents with Tier 3 frontier escalation available."
            ),
            raw_confidence=0.92,
            calibrated_confidence=0.92,
            latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )

    if (doc_count >= 2 and any(sig in q_low for sig in multi_doc_signals)) or any(
        sig in q_low for sig in ("discrepanc", "compare", "follows our", "company policy")
    ):
        return RoutingDecision(
            intent="multi_doc_comparison",
            selected_tier=2,
            rationale=(
                f"Detected multi-document comparison/compliance intent across {doc_count} document(s); "
                "routing to Tier 2 LangGraph Planner + Specialist Agents."
            ),
            raw_confidence=0.94,
            calibrated_confidence=0.94,
            latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )

    if doc_count <= 1 and any(sig in q_low for sig in tier1_signals):
        return RoutingDecision(
            intent="document_classification"
            if "classify" in q_low or "type" in q_low
            else "document_extraction",
            selected_tier=1,
            rationale=(
                "Single-document classification/extraction task; routing to Tier 1 Lightweight AI "
                "to avoid multi-agent and frontier model overhead."
            ),
            raw_confidence=0.91,
            calibrated_confidence=0.91,
            latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )

    # Step 3: Ambiguous query -> use Tier 1 Lightweight AI Classifier
    call = await gateway.invoke(
        workflow_id=workflow_id,
        agent_name="intent_router",
        tier=1,
        task_kind="classify_intent",
        system_prompt=INTENT_ROUTER_SYSTEM_PROMPT,
        user_prompt=f"Query: {query}\nDocument count: {doc_count}\nFilenames: {[d.get('filename') for d in documents]}",
        budget=budget,
        context_payload={"query": query, "doc_count": doc_count},
    )
    data = call.structured_data
    intent = str(data.get("intent", "simple_qa"))
    rec_tier = int(data.get("recommended_tier", 1))
    rec_tier = max(1, min(2, rec_tier))  # Tier 3 is reserved for validated escalation
    rationale = str(
        data.get(
            "rationale",
            f"Tier 1 intent classifier selected Tier {rec_tier} for intent '{intent}'.",
        )
    )
    return RoutingDecision(
        intent=intent,
        selected_tier=rec_tier,
        rationale=rationale,
        raw_confidence=call.raw_confidence,
        calibrated_confidence=call.calibrated_confidence,
        model_log=call.invocation_record,
        latency_ms=round((time.perf_counter() - t0) * 1000.0 + call.latency_ms, 2),
    )
