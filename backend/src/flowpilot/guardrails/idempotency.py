"""Idempotency lookup service preventing duplicate workflow execution & LLM spend."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flowpilot.db.models import Workflow


async def find_existing_idempotent_workflow(
    session: AsyncSession,
    *,
    user_id: str,
    idempotency_key: str | None,
) -> Workflow | None:
    """Return an existing workflow matching (user_id, idempotency_key) if present."""
    if not idempotency_key:
        return None
    stmt = (
        select(Workflow)
        .where(
            Workflow.user_id == user_id,
            Workflow.idempotency_key == idempotency_key,
        )
        .order_by(Workflow.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()
