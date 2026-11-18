"""Unit tests for Tier 0 deterministic path, budget guardrails, circuit breakers, and calibration."""

from __future__ import annotations

import pytest
from flowpilot.benchmarks.dataset import get_enterprise_demo_pack
from flowpilot.config import Settings, normalize_async_db_url
from flowpilot.documents.chunker import estimate_tokens, fit_context
from flowpilot.guardrails.budget import BudgetLimits, DailySpendLedger, WorkflowBudgetTracker
from flowpilot.guardrails.circuit_breaker import CircuitBreaker
from flowpilot.guardrails.exceptions import (
    AgentCallLimitExceededError,
    CircuitBreakerOpenError,
    CostBudgetExceededError,
    EscalationLimitExceededError,
    RetryLimitExceededError,
    StepLimitExceededError,
    TokenBudgetExceededError,
    ToolCallLimitExceededError,
    WorkflowTimeoutError,
)
from flowpilot.llm.calibration import (
    CalibrationSample,
    calibrate_confidence,
    compute_reliability_bins,
    fit_linear_calibration,
    threshold_sweep,
)
from flowpilot.orchestration.tier0 import try_tier0_fast_path


def test_tier0_fast_path_handles_lookup_date_and_calculation_without_llm() -> None:
    pack = {
        d.filename: d.to_state_dict(f"id-{i}") for i, d in enumerate(get_enterprise_demo_pack())
    }
    inv = pack["Invoice_INV-2026-8841.pdf"]

    res_num = try_tier0_fast_path("What is the invoice number?", [inv])
    assert res_num.handled is True
    assert res_num.extracted_fields["document_number"] == "INV-2026-8841"
    assert res_num.confidence == 1.0

    res_date = try_tier0_fast_path("What is the due date?", [inv])
    assert res_date.handled is True
    assert res_date.extracted_fields["due_date"] == "2026-10-29"

    res_total = try_tier0_fast_path("Calculate the invoice total", [inv])
    assert res_total.handled is True
    assert res_total.extracted_fields["total_amount"] == 15768.0
    assert res_total.extracted_fields["arithmetic_check"] == "passed"

    # Complex multi-doc comparison must NOT be swallowed by Tier 0
    res_complex = try_tier0_fast_path(
        "Check whether this invoice follows our purchase order and company policy.",
        [inv],
    )
    assert res_complex.handled is False


def test_fit_context_bounds_tokens_and_preserves_head_and_tail() -> None:
    text = "HEADER_START " + ("lorem ipsum dolor sit amet " * 400) + " FOOTER_END_TOTAL_999"
    bounded = fit_context(text, max_tokens=120)
    assert estimate_tokens(bounded) <= 145
    assert "HEADER_START" in bounded
    assert "FOOTER_END_TOTAL_999" in bounded


def test_all_budget_guardrails_raise_typed_errors() -> None:
    ledger = DailySpendLedger()
    limits = BudgetLimits(
        max_steps=2,
        max_agent_calls=2,
        max_tokens_per_workflow=500,
        max_cost_per_workflow_usd=0.05,
        user_daily_limit_usd=0.08,
        global_daily_limit_usd=0.10,
        timeout_seconds=10.0,
        max_retries=1,
        max_tool_calls_per_agent=2,
        max_escalations=1,
    )
    tracker = WorkflowBudgetTracker(workflow_id="wf-1", user_id="u-1", limits=limits, ledger=ledger)

    # Max steps
    tracker.record_step("s1")
    tracker.record_step("s2")
    with pytest.raises(StepLimitExceededError):
        tracker.record_step("s3")

    # Max agent calls
    tracker.record_agent_call("a1")
    tracker.record_agent_call("a2")
    with pytest.raises(AgentCallLimitExceededError):
        tracker.record_agent_call("a3")

    # Tool-call limit per agent
    tracker.record_tool_call("retrieval", "search")
    tracker.record_tool_call("retrieval", "search")
    with pytest.raises(ToolCallLimitExceededError):
        tracker.record_tool_call("retrieval", "search")

    # Retry limit
    tracker.record_retry("first retry")
    with pytest.raises(RetryLimitExceededError):
        tracker.record_retry("second retry")

    # Escalation limit
    tracker.record_escalation("tier3")
    with pytest.raises(EscalationLimitExceededError):
        tracker.record_escalation("second tier3")

    # Token budget
    with pytest.raises(TokenBudgetExceededError):
        tracker.check_token_and_cost_allowance(projected_tokens=600, projected_cost_usd=0.01)

    # Workflow cost budget
    with pytest.raises(CostBudgetExceededError):
        tracker.check_token_and_cost_allowance(projected_tokens=100, projected_cost_usd=0.06)

    # User daily budget
    ledger.record(user_id="u-1", cost_usd=0.07)
    with pytest.raises(CostBudgetExceededError):
        tracker.check_daily_budgets(projected_cost_usd=0.02)

    # Timeout
    tracker.started_monotonic -= 20.0
    with pytest.raises(WorkflowTimeoutError):
        tracker.check_timeout()


def test_circuit_breaker_transitions() -> None:
    cb = CircuitBreaker(key="openai:tier3", failure_threshold=2, recovery_seconds=60)
    cb.allow_request()
    cb.record_failure()
    assert cb.state == "closed"
    cb.record_failure()
    assert cb.state == "open"
    with pytest.raises(CircuitBreakerOpenError):
        cb.allow_request()

    # Simulate recovery window elapsed -> half_open -> success closes
    cb.opened_at = (cb.opened_at or 0.0) - 65.0
    cb.allow_request()
    assert cb.state == "half_open"
    cb.record_success()
    assert cb.state == "closed"


def test_calibration_ece_linear_fit_and_bidirectional_sweep() -> None:
    samples = [
        CalibrationSample(0.95, calibrate_confidence(0.95), True),
        CalibrationSample(0.90, calibrate_confidence(0.90), True),
        CalibrationSample(0.85, calibrate_confidence(0.85), True),
        CalibrationSample(0.60, calibrate_confidence(0.60), False),
        CalibrationSample(0.55, calibrate_confidence(0.55), False),
    ]
    ece, bins = compute_reliability_bins(samples, num_bins=5)
    assert 0.0 <= ece <= 1.0
    assert len(bins) == 5

    slope, intercept = fit_linear_calibration(samples)
    assert 0.25 <= slope <= 1.25
    assert isinstance(intercept, float)

    sweep_hi = threshold_sweep([0.9, 0.7, 0.3], [True, True, False], [0.5, 0.8], direction="high")
    sweep_lo = threshold_sweep([0.1, 0.4, 0.9], [True, False, False], [0.2, 0.5], direction="low")
    assert sweep_hi[0]["f1"] == 1.0
    assert sweep_lo[0]["f1"] == 1.0


def test_config_normalization_and_production_guard() -> None:
    assert normalize_async_db_url("postgres://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"
    assert normalize_async_db_url("postgresql://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"
    with pytest.raises(ValueError, match="FLOWPILOT_SECRET_KEY"):
        Settings(env="production")
