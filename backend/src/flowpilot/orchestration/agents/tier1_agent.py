"""Tier 1 Lightweight AI Agent: document classification, single-doc extraction, simple QA."""

from __future__ import annotations

from typing import Any

from flowpilot.guardrails.budget import WorkflowBudgetTracker
from flowpilot.llm.gateway import ModelGateway
from flowpilot.orchestration.prompts import EXTRACTION_SYSTEM_PROMPT
from flowpilot.orchestration.tier0 import extract_structured_record


async def run_tier1_lightweight(
    *,
    workflow_id: str,
    query: str,
    intent: str,
    documents: list[dict[str, Any]],
    gateway: ModelGateway,
    budget: WorkflowBudgetTracker,
) -> dict[str, Any]:
    """Handle classification, entity extraction, or simple QA using a small lightweight model."""
    budget.record_agent_call("extraction")
    doc = (
        documents[0]
        if documents
        else {"id": "", "filename": "none", "doc_type": "unknown", "raw_text": ""}
    )
    record = extract_structured_record(doc)
    record_dict = record.model_dump()

    if intent == "document_classification":
        call = await gateway.invoke(
            workflow_id=workflow_id,
            agent_name="extraction",
            tier=1,
            task_kind="classify_document",
            system_prompt="Classify the document type and provide a concise one-sentence justification in JSON.",
            user_prompt=f"Filename: {doc.get('filename')}\nContent:\n{doc.get('raw_text', '')}",
            budget=budget,
            context_payload={"filename": doc.get("filename"), "text": doc.get("raw_text", "")},
        )
        doc_type = str(
            call.structured_data.get("doc_type") or doc.get("doc_type") or "general_document"
        )
        summary = str(call.structured_data.get("summary") or "")
        record_dict["doc_type"] = doc_type
        return {
            "answer": f"Classified **{doc.get('filename')}** as **{doc_type.replace('_', ' ')}**. {summary}".strip(),
            "doc_type": doc_type,
            "extracted_records": [record_dict],
            "raw_confidence": call.raw_confidence,
            "calibrated_confidence": call.calibrated_confidence,
            "model_log": call.invocation_record,
        }

    # Structured entity extraction or simple QA
    populated_fields = sum(
        1
        for k in ("document_number", "vendor", "issue_date", "total_amount", "payment_terms")
        if record_dict.get(k) is not None
    )
    completeness = 0.78 + min(0.18, populated_fields * 0.04)

    call = await gateway.invoke(
        workflow_id=workflow_id,
        agent_name="extraction",
        tier=1,
        task_kind="extract_structured" if intent == "document_extraction" else "simple_qa",
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        user_prompt=f"Query: {query}\nDocument ({doc.get('filename')}):\n{doc.get('raw_text', '')}",
        budget=budget,
        context_payload={
            "pre_extracted": record_dict,
            "completeness_score": completeness,
            "text": doc.get("raw_text", ""),
        },
    )

    if intent == "document_extraction":
        highlights = []
        if record.document_number:
            highlights.append(f"Number: **{record.document_number}**")
        if record.vendor:
            highlights.append(f"Vendor: **{record.vendor}**")
        if record.issue_date:
            highlights.append(f"Date: **{record.issue_date}**")
        if record.total_amount is not None:
            highlights.append(f"Total: **${record.total_amount:,.2f}**")
        if record.payment_terms:
            highlights.append(f"Terms: **{record.payment_terms}**")
        answer = f"Extracted structured fields from **{record.filename}** ({record.doc_type}): " + (
            ", ".join(highlights) if highlights else "See structured fields below."
        )
    else:
        answer = str(
            call.structured_data.get("answer")
            or call.structured_data.get("text")
            or f"Answered query using {record.filename}."
        )

    return {
        "answer": answer,
        "doc_type": record.doc_type,
        "extracted_records": [record_dict],
        "raw_confidence": call.raw_confidence,
        "calibrated_confidence": call.calibrated_confidence,
        "model_log": call.invocation_record,
    }
