"""Pydantic v2 schemas for budget policies, guardrails, and circuit breakers."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BudgetPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    scope: str
    user_id: str | None
    task_type: str | None
    max_steps: int
    max_agent_calls: int
    max_tokens_per_workflow: int
    max_cost_per_workflow_usd: float
    daily_cost_limit_usd: float
    timeout_seconds: int
    max_retries: int
    max_tool_calls_per_agent: int
    max_escalations: int
    confidence_threshold: float
    is_active: bool
    updated_at: datetime


class BudgetPolicyUpdate(BaseModel):
    max_steps: int | None = Field(default=None, ge=1, le=50)
    max_agent_calls: int | None = Field(default=None, ge=1, le=50)
    max_tokens_per_workflow: int | None = Field(default=None, ge=500, le=200_000)
    max_cost_per_workflow_usd: float | None = Field(default=None, ge=0.01, le=50.0)
    daily_cost_limit_usd: float | None = Field(default=None, ge=0.10, le=10_000.0)
    timeout_seconds: int | None = Field(default=None, ge=5, le=300)
    max_retries: int | None = Field(default=None, ge=0, le=5)
    max_tool_calls_per_agent: int | None = Field(default=None, ge=1, le=20)
    max_escalations: int | None = Field(default=None, ge=0, le=3)
    confidence_threshold: float | None = Field(default=None, ge=0.1, le=0.99)
    is_active: bool | None = None


class CircuitBreakerStatusOut(BaseModel):
    key: str
    state: str
    failure_count: int
    failure_threshold: int
    recovery_seconds: int
    opened_at: float | None = None


class BudgetSummaryOut(BaseModel):
    global_daily_spend_usd: float
    global_daily_limit_usd: float
    user_daily_spend_usd: float
    user_daily_limit_usd: float
    active_policies: list[BudgetPolicyOut]
    circuit_breakers: list[CircuitBreakerStatusOut]
