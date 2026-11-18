"""Budget policies, daily spend tracking, and circuit breaker management routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from flowpilot.api.deps import CurrentUserDep, SessionDep
from flowpilot.config import get_settings
from flowpilot.db.models import BudgetPolicy
from flowpilot.guardrails.budget import get_daily_spend_ledger
from flowpilot.guardrails.circuit_breaker import get_circuit_breaker_registry
from flowpilot.schemas.budgets import (
    BudgetPolicyOut,
    BudgetPolicyUpdate,
    BudgetSummaryOut,
    CircuitBreakerStatusOut,
)

router = APIRouter(prefix="/api/v1/budgets", tags=["budgets"])


@router.get("", response_model=BudgetSummaryOut)
async def get_budget_summary(user: CurrentUserDep, session: SessionDep) -> BudgetSummaryOut:
    settings = get_settings()
    rows = list(
        (await session.execute(select(BudgetPolicy).order_by(BudgetPolicy.scope))).scalars().all()
    )
    ledger = get_daily_spend_ledger()
    global_pol = next((p for p in rows if p.scope == "global" and p.is_active), None)
    user_pol = next(
        (p for p in rows if p.scope == "user" and p.user_id == user.id and p.is_active), None
    )

    breakers = [
        CircuitBreakerStatusOut.model_validate(b) for b in get_circuit_breaker_registry().list_all()
    ]
    return BudgetSummaryOut(
        global_daily_spend_usd=ledger.get_global_spend(),
        global_daily_limit_usd=global_pol.daily_cost_limit_usd
        if global_pol
        else settings.global_daily_budget_usd,
        user_daily_spend_usd=ledger.get_user_spend(user.id),
        user_daily_limit_usd=user_pol.daily_cost_limit_usd
        if user_pol
        else settings.default_user_daily_budget_usd,
        active_policies=[BudgetPolicyOut.model_validate(r) for r in rows],
        circuit_breakers=breakers,
    )


@router.patch("/{policy_id}", response_model=BudgetPolicyOut)
async def update_budget_policy(
    policy_id: str,
    payload: BudgetPolicyUpdate,
    _user: CurrentUserDep,
    session: SessionDep,
) -> BudgetPolicyOut:
    res = await session.execute(select(BudgetPolicy).where(BudgetPolicy.id == policy_id))
    policy = res.scalar_one_or_none()
    if policy is None:
        raise HTTPException(status_code=404, detail="Budget policy not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(policy, field, value)
    await session.commit()
    await session.refresh(policy)
    return BudgetPolicyOut.model_validate(policy)


@router.get("/circuit-breakers", response_model=list[CircuitBreakerStatusOut])
async def list_circuit_breakers(_user: CurrentUserDep) -> list[CircuitBreakerStatusOut]:
    return [
        CircuitBreakerStatusOut.model_validate(b) for b in get_circuit_breaker_registry().list_all()
    ]


@router.post("/circuit-breakers/{breaker_key:path}/reset")
async def reset_circuit_breaker(breaker_key: str, _user: CurrentUserDep) -> dict[str, object]:
    ok = get_circuit_breaker_registry().reset(breaker_key)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Circuit breaker '{breaker_key}' not found.")
    return {"key": breaker_key, "state": "closed"}
