"""Typed guardrail and reliability exceptions for structured failure handling."""

from __future__ import annotations

from typing import Any


class GuardrailViolationError(Exception):
    """Base exception raised when a production guardrail stops execution."""

    guardrail_type: str = "generic_guardrail"
    http_status: int = 429

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_error_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.guardrail_type,
            "message": self.message,
            "details": self.details,
        }


class StepLimitExceededError(GuardrailViolationError):
    guardrail_type = "max_steps"


class AgentCallLimitExceededError(GuardrailViolationError):
    guardrail_type = "max_agent_calls"


class TokenBudgetExceededError(GuardrailViolationError):
    guardrail_type = "token_budget"


class CostBudgetExceededError(GuardrailViolationError):
    guardrail_type = "cost_budget"


class ToolCallLimitExceededError(GuardrailViolationError):
    guardrail_type = "tool_call_limit"


class RetryLimitExceededError(GuardrailViolationError):
    guardrail_type = "retry_limit"


class EscalationLimitExceededError(GuardrailViolationError):
    guardrail_type = "escalation_limit"


class WorkflowTimeoutError(GuardrailViolationError):
    guardrail_type = "execution_timeout"
    http_status = 504


class WorkflowCancelledError(GuardrailViolationError):
    guardrail_type = "workflow_cancelled"
    http_status = 499


class CircuitBreakerOpenError(GuardrailViolationError):
    guardrail_type = "circuit_breaker_open"
    http_status = 503
