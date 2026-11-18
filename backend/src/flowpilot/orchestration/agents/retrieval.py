"""Retrieval Agent: hybrid pgvector + lexical chunk retrieval with bounded tool calls."""

from __future__ import annotations

import time
from typing import Any

from flowpilot.documents.repository import DocumentRepository
from flowpilot.guardrails.budget import WorkflowBudgetTracker


async def run_retrieval_agent(
    *,
    query: str,
    documents: list[dict[str, Any]],
    repo: DocumentRepository | None,
    budget: WorkflowBudgetTracker,
    top_k: int = 8,
) -> dict[str, Any]:
    """Retrieve high-signal document chunks via hybrid search, logging each tool invocation."""
    budget.record_agent_call("retrieval")
    budget.record_tool_call("retrieval", "hybrid_vector_search")

    t0 = time.perf_counter()
    doc_ids = [str(d["id"]) for d in documents if d.get("id")]
    chunks: list[dict[str, Any]] = []

    if repo is not None and doc_ids:
        found = await repo.hybrid_search(query=query, document_ids=doc_ids, top_k=top_k)
        chunks = [c.model_dump() for c in found]

    # Fallback directly to raw document excerpts when operating in pure in-memory benchmark mode
    if not chunks:
        for idx, d in enumerate(documents):
            chunks.append(
                {
                    "chunk_id": f"mem-{idx}",
                    "document_id": str(d.get("id", f"doc-{idx}")),
                    "filename": str(d.get("filename", f"doc-{idx}.pdf")),
                    "doc_type": str(d.get("doc_type", "general_document")),
                    "page_number": 1,
                    "section_title": "Full Text",
                    "content": str(d.get("raw_text", ""))[:2000],
                    "score": 0.9,
                }
            )

    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    tool_log = {
        "agent_name": "retrieval",
        "tool_name": "hybrid_vector_search",
        "arguments_json": {"query": query[:120], "doc_count": len(doc_ids), "top_k": top_k},
        "result_summary_json": {"chunks_returned": len(chunks)},
        "latency_ms": latency_ms,
        "status": "success",
        "error_message": None,
    }
    return {"retrieved_chunks": chunks, "tool_logs": [tool_log]}
