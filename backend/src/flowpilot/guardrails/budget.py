"""Workflow, per-user, and global budget guardrail enforcement."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from flowpilot.guardrails.exceptions import (
    AgentCallLimitExceededError,
    CostBudgetExceededError,
    EscalationLimitExceededError,
    RetryLimitExceededError,
    StepLimitExceededError,
    TokenBudgetExceededError,
    ToolCallLimitExceededError,
    WorkflowTimeoutError,
)
from flowpilot.observability.metrics import GUARDRAIL_TRIPS_TOTAL


@dataclass(slots=True)
class BudgetLimits:
    """Resolved runtime limits for a single workflow execution."""

    max_steps: int = 12
    max_agent_calls: int = 15
    max_tokens_per_workflow: int = 10_000
    max_cost_per_workflow_usd: float = 0.50
    user_daily_limit_usd: float = 15.0
    global_daily_limit_usd: float = 100.0
    timeout_seconds: float = 60.0
    max_retries: int = 2
    max_tool_calls_per_agent: int = 5
    max_escalations: int = 1
    confidence_threshold: float = 0.80


class DailySpendLedger:
    """Tracks global and per-user UTC daily USD spend (in-process + synced with DB/Redis)."""

    def __init__(self) -> None:
        self._day_key: str = self._today()
        self._global_spend: float = 0.0
        self._user_spend: dict[str, float] = defaultdict(float)

    @staticmethod
    def _today() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def _roll_if_needed(self) -> None:
        today = self._today()
        if today != self._day_key:
            self._day_key = today
            self._global_spend = 0.0
            self._user_spend.clear()

    def record(self, *, user_id: str, cost_usd: float) -> None:
        self._roll_if_needed()
        self._global_spend += cost_usd
        self._user_spend[user_id] += cost_usd

    def get_global_spend(self) -> float:
        self._roll_if_needed()
        return round(self._global_spend, 6)

    def get_user_spend(self, user_id: str) -> float:
        self._roll_if_needed()
        return round(self._user_spend.get(user_id, 0.0), 6)

    def reset(self) -> None:
        self._global_spend = 0.0
        self._user_spend.clear()


_daily_ledger = DailySpendLedger()


def get_daily_spend_ledger() -> DailySpendLedger:
    return _daily_ledger


@dataclass
class WorkflowBudgetTracker:
    """Mutable per-workflow budget enforcer injected into every LangGraph node."""

    workflow_id: str
    user_id: str
    limits: BudgetLimits = field(default_factory=BudgetLimits)
    ledger: DailySpendLedger = field(default_factory=get_daily_spend_ledger)

    started_monotonic: float = field(default_factory=time.monotonic)
    steps: int = 0
    agent_calls: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    retries: int = 0
    escalations: int = 0
    tool_calls_by_agent: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def check_timeout(self) -> None:
        elapsed = time.monotonic() - self.started_monotonic
        if elapsed > self.limits.timeout_seconds:
            GUARDRAIL_TRIPS_TOTAL.labels(guardrail_type="execution_timeout").inc()
            raise WorkflowTimeoutError(
                f"Workflow exceeded execution timeout of {self.limits.timeout_seconds}s "
                f"(elapsed: {elapsed:.2f}s).",
                details={
                    "elapsed_seconds": round(elapsed, 2),
                    "limit": self.limits.timeout_seconds,
                },
            )

    def check_daily_budgets(self, *, projected_cost_usd: float = 0.0) -> None:
        global_total = self.ledger.get_global_spend() + projected_cost_usd
        if global_total > self.limits.global_daily_limit_usd:
            GUARDRAIL_TRIPS_TOTAL.labels(guardrail_type="global_daily_budget").inc()
            raise CostBudgetExceededError(
                f"Global daily spend limit (${self.limits.global_daily_limit_usd:.2f}) exceeded.",
                details={
                    "scope": "global",
                    "current_usd": round(self.ledger.get_global_spend(), 4),
                    "limit_usd": self.limits.global_daily_limit_usd,
                },
            )
        user_total = self.ledger.get_user_spend(self.user_id) + projected_cost_usd
        if user_total > self.limits.user_daily_limit_usd:
            GUARDRAIL_TRIPS_TOTAL.labels(guardrail_type="user_daily_budget").inc()
            raise CostBudgetExceededError(
                f"User daily spend limit (${self.limits.user_daily_limit_usd:.2f}) exceeded.",
                details={
                    "scope": "user",
                    "user_id": self.user_id,
                    "current_usd": round(self.ledger.get_user_spend(self.user_id), 4),
                    "limit_usd": self.limits.user_daily_limit_usd,
                },
            )

    def record_step(self, node_name: str) -> None:
        self.check_timeout()
        if self.steps + 1 > self.limits.max_steps:
            GUARDRAIL_TRIPS_TOTAL.labels(guardrail_type="max_steps").inc()
            raise StepLimitExceededError(
                f"Maximum step limit ({self.limits.max_steps}) reached before '{node_name}'.",
                details={
                    "steps": self.steps,
                    "max_steps": self.limits.max_steps,
                    "node": node_name,
                },
            )
        self.steps += 1

    def record_agent_call(self, agent_name: str) -> None:
        self.check_timeout()
        if self.agent_calls + 1 > self.limits.max_agent_calls:
            GUARDRAIL_TRIPS_TOTAL.labels(guardrail_type="max_agent_calls").inc()
            raise AgentCallLimitExceededError(
                f"Maximum agent calls ({self.limits.max_agent_calls}) exceeded at '{agent_name}'.",
                details={
                    "agent_calls": self.agent_calls,
                    "max_agent_calls": self.limits.max_agent_calls,
                    "agent": agent_name,
                },
            )
        self.agent_calls += 1

    def record_tool_call(self, agent_name: str, tool_name: str) -> None:
        self.check_timeout()
        current = self.tool_calls_by_agent[agent_name]
        if current + 1 > self.limits.max_tool_calls_per_agent:
            GUARDRAIL_TRIPS_TOTAL.labels(guardrail_type="tool_call_limit").inc()
            raise ToolCallLimitExceededError(
                f"Agent '{agent_name}' exceeded tool-call limit ({self.limits.max_tool_calls_per_agent}) "
                f"attempting '{tool_name}'.",
                details={
                    "agent": agent_name,
                    "tool": tool_name,
                    "tool_calls": current,
                    "limit": self.limits.max_tool_calls_per_agent,
                },
            )
        self.tool_calls_by_agent[agent_name] = current + 1

    def check_token_and_cost_allowance(
        self,
        *,
        projected_tokens: int,
        projected_cost_usd: float = 0.0,
    ) -> None:
        self.check_timeout()
        self.check_daily_budgets(projected_cost_usd=projected_cost_usd)
        if self.tokens + projected_tokens > self.limits.max_tokens_per_workflow:
            GUARDRAIL_TRIPS_TOTAL.labels(guardrail_type="token_budget").inc()
            raise TokenBudgetExceededError(
                f"Workflow token budget ({self.limits.max_tokens_per_workflow}) would be exceeded "
                f"(used={self.tokens}, requested={projected_tokens}).",
                details={
                    "used_tokens": self.tokens,
                    "projected_tokens": projected_tokens,
                    "max_tokens": self.limits.max_tokens_per_workflow,
                },
            )
        if self.cost_usd + projected_cost_usd > self.limits.max_cost_per_workflow_usd:
            GUARDRAIL_TRIPS_TOTAL.labels(guardrail_type="cost_budget").inc()
            raise CostBudgetExceededError(
                f"Workflow cost budget (${self.limits.max_cost_per_workflow_usd:.4f}) exceeded.",
                details={
                    "used_cost_usd": round(self.cost_usd, 6),
                    "projected_cost_usd": round(projected_cost_usd, 6),
                    "limit_usd": self.limits.max_cost_per_workflow_usd,
                },
            )

    def commit_usage(self, *, tokens: int, cost_usd: float) -> None:
        self.tokens += tokens
        self.cost_usd += cost_usd
        if cost_usd > 0:
            self.ledger.record(user_id=self.user_id, cost_usd=cost_usd)

    def can_retry(self) -> bool:
        return self.retries < self.limits.max_retries

    def record_retry(self, reason: str) -> None:
        if self.retries + 1 > self.limits.max_retries:
            GUARDRAIL_TRIPS_TOTAL.labels(guardrail_type="retry_limit").inc()
            raise RetryLimitExceededError(
                f"Retry limit ({self.limits.max_retries}) exceeded: {reason}",
                details={"retries": self.retries, "limit": self.limits.max_retries},
            )
        self.retries += 1

    def can_escalate(self) -> bool:
        return self.escalations < self.limits.max_escalations

    def record_escalation(self, reason: str) -> None:
        if self.escalations + 1 > self.limits.max_escalations:
            GUARDRAIL_TRIPS_TOTAL.labels(guardrail_type="escalation_limit").inc()
            raise EscalationLimitExceededError(
                f"Frontier escalation limit ({self.limits.max_escalations}) exceeded: {reason}",
                details={"escalations": self.escalations, "limit": self.limits.max_escalations},
            )
        self.escalations += 1

    @property
    def total_tool_calls(self) -> int:
        return sum(self.tool_calls_by_agent.values())

    def snapshot(self) -> dict[str, Any]:
        return {
            "steps": self.steps,
            "max_steps": self.limits.max_steps,
            "agent_calls": self.agent_calls,
            "max_agent_calls": self.limits.max_agent_calls,
            "tokens": self.tokens,
            "max_tokens": self.limits.max_tokens_per_workflow,
            "cost_usd": round(self.cost_usd, 6),
            "max_cost_usd": self.limits.max_cost_per_workflow_usd,
            "retries": self.retries,
            "max_retries": self.limits.max_retries,
            "escalations": self.escalations,
            "max_escalations": self.limits.max_escalations,
            "tool_calls": self.total_tool_calls,
            "elapsed_ms": round((time.monotonic() - self.started_monotonic) * 1000, 2),
        }
