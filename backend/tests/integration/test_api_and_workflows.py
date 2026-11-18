"""Integration tests for FastAPI routes, PyMuPDF ingestion, Tier 0-3 workflows, and guardrails."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_metrics_and_langgraph_mermaid(client: AsyncClient) -> None:
    health = await client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    mermaid = await client.get("/api/v1/workflows/graph/mermaid")
    assert mermaid.status_code == 200
    diagram = mermaid.json()["mermaid"]
    assert "intent_router" in diagram
    assert "tier0_fast_path" in diagram
    assert "reasoning_tier3" in diagram

    metrics = await client.get("/metrics")
    assert metrics.status_code == 200
    assert "flowpilot_workflows_total" in metrics.text


@pytest.mark.asyncio
async def test_tiered_end_to_end_workflows_and_telemetry_separation(client: AsyncClient) -> None:
    # 1. Load Enterprise Demo Pack (5 real PDFs parsed by PyMuPDF + chunked + embedded)
    pack_resp = await client.post("/api/v1/documents/demo-pack")
    assert pack_resp.status_code == 200
    docs = pack_resp.json()
    assert len(docs) == 5
    by_name = {d["filename"]: d for d in docs}
    inv_id = by_name["Invoice_INV-2026-8841.pdf"]["id"]
    po_id = by_name["PurchaseOrder_PO-2026-4410.pdf"]["id"]
    pol_id = by_name["CompanyPolicy_Procurement_v4.pdf"]["id"]
    ctr_a_id = by_name["MasterServicesAgreement_A.pdf"]["id"]
    ctr_b_id = by_name["OrderFormAddendum_B.pdf"]["id"]

    # 2. Tier 0 Deterministic Fast Path (ZERO LLM tokens)
    t0 = await client.post(
        "/api/v1/workflows/execute",
        json={"query": "What is the invoice number?", "document_ids": [inv_id]},
    )
    assert t0.status_code == 200
    t0_data = t0.json()
    assert t0_data["final_tier"] == 0
    assert t0_data["total_tokens"] == 0
    assert t0_data["total_cost_usd"] == 0.0
    assert len(t0_data["model_invocations"]) == 0
    assert "INV-2026-8841" in t0_data["final_response_json"]["summary"]
    assert "planner" in t0_data["skipped_agents"]
    assert "reasoning" in t0_data["skipped_agents"]

    # 3. Tier 0 Cache Hit on repeated identical query
    t0_cached = await client.post(
        "/api/v1/workflows/execute",
        json={"query": "What is the invoice number?", "document_ids": [inv_id]},
    )
    assert t0_cached.status_code == 200
    assert t0_cached.json()["cache_hit"] is True
    assert t0_cached.json()["total_tokens"] == 0

    # 4. Tier 1 Lightweight AI (Classification)
    t1 = await client.post(
        "/api/v1/workflows/execute",
        json={
            "query": "Classify whether this document is an invoice or a contract.",
            "document_ids": [inv_id],
        },
    )
    assert t1.status_code == 200
    t1_data = t1.json()
    assert t1_data["final_tier"] == 1
    assert len(t1_data["model_invocations"]) == 1
    assert "invoice" in t1_data["final_response_json"]["summary"].lower()
    assert "comparison" in t1_data["skipped_agents"]

    # 5. Tier 2 Multi-Agent 3-Way Compliance Comparison (Invoice + PO + Policy)
    t2 = await client.post(
        "/api/v1/workflows/execute",
        json={
            "query": "Check whether this invoice follows our purchase order and company policy. Identify any discrepancies.",
            "document_ids": [inv_id, po_id, pol_id],
        },
    )
    assert t2.status_code == 200
    t2_data = t2.json()
    assert t2_data["final_tier"] == 2
    assert t2_data["escalation_count"] == 0
    disc_codes = {d["code"] for d in t2_data["final_response_json"]["discrepancies"]}
    assert "INV_PO_TOTAL_MISMATCH" in disc_codes
    assert "LINE_QTY_MISMATCH" in disc_codes
    assert "LINE_PRICE_MISMATCH" in disc_codes
    assert "POLICY_APPROVAL_THRESHOLD" in disc_codes
    assert "POLICY_VARIANCE_EXCEEDED" in disc_codes
    assert len(t2_data["steps"]) >= 5
    assert len(t2_data["model_invocations"]) >= 1
    assert len(t2_data["tool_invocations"]) >= 2
    assert t2_data["savings_usd"] > 0

    # 6. Tier 3 Frontier Escalation (Conflicting Contracts)
    t3 = await client.post(
        "/api/v1/workflows/execute",
        json={
            "query": "Compare these two contracts and resolve conflicting indemnification, liability cap, and governing law terms.",
            "document_ids": [ctr_a_id, ctr_b_id],
        },
    )
    assert t3.status_code == 200
    t3_data = t3.json()
    assert t3_data["final_tier"] == 3
    assert t3_data["escalation_count"] == 1
    assert t3_data["final_response_json"]["frontier_reasoning"] is not None

    # 7. Idempotency replay returns identical workflow_id without re-executing
    idem_1 = await client.post(
        "/api/v1/workflows/execute?bypass_cache=true",
        headers={"Idempotency-Key": "req-idem-001"},
        json={"query": "What is the due date?", "document_ids": [inv_id]},
    )
    idem_2 = await client.post(
        "/api/v1/workflows/execute?bypass_cache=true",
        headers={"Idempotency-Key": "req-idem-001"},
        json={"query": "What is the due date?", "document_ids": [inv_id]},
    )
    assert idem_1.json()["id"] == idem_2.json()["id"]

    # 8. Analytics & Guardrails endpoints reflect real persisted telemetry
    analytics = await client.get("/api/v1/analytics/overview")
    assert analytics.status_code == 200
    ov = analytics.json()
    assert ov["total_workflows"] >= 5
    assert ov["tier_distribution"]["tier_0"] >= 2
    assert ov["tier_distribution"]["tier_2"] >= 1
    assert ov["tier_distribution"]["tier_3"] >= 1


@pytest.mark.asyncio
async def test_budget_policy_update_enforces_token_cap_gracefully(client: AsyncClient) -> None:
    pack = (await client.post("/api/v1/documents/demo-pack")).json()
    doc_ids = [d["id"] for d in pack[:3]]

    budgets = (await client.get("/api/v1/budgets")).json()
    user_pol = next(p for p in budgets["active_policies"] if p["scope"] == "user")

    # Tighten token budget to trigger structured TokenBudgetExceededError on Tier 2 workflow
    patch = await client.patch(
        f"/api/v1/budgets/{user_pol['id']}",
        json={"max_tokens_per_workflow": 500},
    )
    assert patch.status_code == 200
    assert patch.json()["max_tokens_per_workflow"] == 500

    wf = await client.post(
        "/api/v1/workflows/execute?bypass_cache=true",
        json={
            "query": "Check whether this invoice follows our purchase order and company policy.",
            "document_ids": doc_ids,
        },
    )
    assert wf.status_code == 200
    data = wf.json()
    assert data["status"] == "budget_exceeded"
    assert data["error_json"]["error_type"] == "token_budget"
