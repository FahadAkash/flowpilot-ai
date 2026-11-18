"""Workflow execution, trace inspection, cancellation, and Mermaid graph routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from flowpilot.api.deps import CurrentUserDep, SessionDep
from flowpilot.db.models import Workflow
from flowpilot.guardrails.cancellation import get_cancellation_registry
from flowpilot.orchestration.graph import get_graph_mermaid_diagram
from flowpilot.orchestration.runner import WorkflowOrchestratorService
from flowpilot.schemas.workflows import (
    ModelInvocationOut,
    ToolInvocationOut,
    WorkflowExecuteRequest,
    WorkflowOut,
    WorkflowStepOut,
    WorkflowTraceOut,
)

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


@router.get("/graph/mermaid")
async def workflow_graph_mermaid() -> dict[str, str]:
    """Return the compiled LangGraph Mermaid diagram."""
    return {"mermaid": get_graph_mermaid_diagram()}


@router.post("/execute", response_model=WorkflowTraceOut)
async def execute_workflow(
    payload: WorkflowExecuteRequest,
    user: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    bypass_cache: bool = Query(default=False),
) -> WorkflowTraceOut:
    service = WorkflowOrchestratorService(session)
    wf = await service.execute_workflow(
        user_id=user.id,
        query=payload.query,
        document_ids=payload.document_ids,
        idempotency_key=idempotency_key,
        force_tier=payload.force_tier,
        confidence_override=payload.confidence_threshold_override,
        bypass_cache=bypass_cache,
    )
    return await _load_trace(session, wf.id, user.id)


@router.get("", response_model=list[WorkflowOut])
async def list_workflows(
    user: CurrentUserDep,
    session: SessionDep,
    limit: int = Query(default=30, ge=1, le=200),
) -> list[WorkflowOut]:
    stmt = (
        select(Workflow)
        .where(Workflow.user_id == user.id)
        .order_by(Workflow.created_at.desc())
        .limit(limit)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return [WorkflowOut.model_validate(r) for r in rows]


@router.get("/{workflow_id}", response_model=WorkflowTraceOut)
async def get_workflow_trace(
    workflow_id: str,
    user: CurrentUserDep,
    session: SessionDep,
) -> WorkflowTraceOut:
    return await _load_trace(session, workflow_id, user.id)


@router.post("/{workflow_id}/cancel")
async def cancel_workflow(
    workflow_id: str,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, str]:
    res = await session.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.user_id == user.id)
    )
    wf = res.scalar_one_or_none()
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    get_cancellation_registry().request_cancel(workflow_id)
    if wf.status in {"queued", "running"}:
        wf.status = "cancelled"
        await session.commit()
    return {"workflow_id": workflow_id, "status": "cancel_requested"}


async def _load_trace(session: SessionDep, workflow_id: str, user_id: str) -> WorkflowTraceOut:
    stmt = (
        select(Workflow)
        .options(
            selectinload(Workflow.steps),
            selectinload(Workflow.model_invocations),
            selectinload(Workflow.tool_invocations),
            selectinload(Workflow.metrics),
        )
        .where(Workflow.id == workflow_id, Workflow.user_id == user_id)
    )
    wf = (await session.execute(stmt)).scalar_one_or_none()
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    base = WorkflowOut.model_validate(wf).model_dump()
    skipped = list((wf.final_response_json or {}).get("skipped_agents") or [])
    return WorkflowTraceOut(
        **base,
        steps=[WorkflowStepOut.model_validate(s) for s in wf.steps],
        model_invocations=[ModelInvocationOut.model_validate(m) for m in wf.model_invocations],
        tool_invocations=[ToolInvocationOut.model_validate(t) for t in wf.tool_invocations],
        estimated_baseline_cost_usd=wf.metrics.estimated_baseline_cost_usd if wf.metrics else 0.0,
        estimated_baseline_tokens=wf.metrics.estimated_baseline_tokens if wf.metrics else 0,
        savings_usd=wf.metrics.savings_usd if wf.metrics else 0.0,
        skipped_agents=skipped,
    )
