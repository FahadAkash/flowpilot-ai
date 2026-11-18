"""Celery tasks bridging synchronous worker threads to async FlowPilot services."""

from __future__ import annotations

import asyncio
from typing import Any

from flowpilot.db.session import get_session_factory
from flowpilot.orchestration.runner import WorkflowOrchestratorService
from flowpilot.workers.celery_app import celery_app


@celery_app.task(name="flowpilot.execute_workflow_task")
def execute_workflow_task(
    *,
    user_id: str,
    query: str,
    document_ids: list[str],
    idempotency_key: str | None = None,
    force_tier: int | None = None,
) -> dict[str, Any]:
    """Run a FlowPilot workflow asynchronously inside a Celery worker."""

    async def _run() -> dict[str, Any]:
        factory = get_session_factory()
        async with factory() as session:
            service = WorkflowOrchestratorService(session)
            wf = await service.execute_workflow(
                user_id=user_id,
                query=query,
                document_ids=document_ids,
                idempotency_key=idempotency_key,
                force_tier=force_tier,
            )
            return {
                "workflow_id": wf.id,
                "status": wf.status,
                "final_tier": wf.final_tier,
                "total_tokens": wf.total_tokens,
                "total_cost_usd": wf.total_cost_usd,
            }

    return asyncio.run(_run())
