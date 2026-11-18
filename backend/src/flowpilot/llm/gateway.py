"""Unified ModelGateway with context budgeting, guardrails, circuit breaking, and cost accounting."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from flowpilot.config import get_settings
from flowpilot.documents.chunker import estimate_tokens, fit_context
from flowpilot.guardrails.budget import WorkflowBudgetTracker
from flowpilot.guardrails.cancellation import get_cancellation_registry
from flowpilot.guardrails.circuit_breaker import get_circuit_breaker_registry
from flowpilot.llm.calibration import calibrate_confidence
from flowpilot.llm.providers import BaseLLMProvider, resolve_provider
from flowpilot.observability.metrics import COST_USD_TOTAL, TOKENS_TOTAL

MODEL_PRICING_PER_1K: dict[str, tuple[float, float]] = {
    "deterministic-tier0": (0.0, 0.0),
    "google/gemma-4-12b-qat": (0.0, 0.0),
    "gpt-4o-mini": (0.00015, 0.00060),
    "gemini-2.5-flash-lite": (0.00010, 0.00040),
    "llama-3.1-8b-local": (0.0, 0.0),
    "gpt-4o": (0.00250, 0.01000),
    "claude-3-7-sonnet": (0.00300, 0.01500),
    "gemini-2.5-pro": (0.00125, 0.01000),
}

MODEL_CALIBRATION_PARAMS: dict[str, tuple[float, float]] = {
    "deterministic-tier0": (1.0, 0.0),
    "google/gemma-4-12b-qat": (0.94, 0.03),
    "gpt-4o-mini": (0.92, 0.04),
    "gemini-2.5-flash-lite": (0.94, 0.03),
    "llama-3.1-8b-local": (0.88, 0.05),
    "gpt-4o": (0.97, 0.01),
    "claude-3-7-sonnet": (0.98, 0.01),
    "gemini-2.5-pro": (0.96, 0.02),
}


def compute_cost_usd(model_key: str, *, prompt_tokens: int, completion_tokens: int) -> float:
    in_rate, out_rate = MODEL_PRICING_PER_1K.get(model_key, (0.0005, 0.0015))
    return round((prompt_tokens / 1000.0) * in_rate + (completion_tokens / 1000.0) * out_rate, 7)


@dataclass(slots=True)
class ModelCallResult:
    model_key: str
    provider: str
    tier: int
    agent_name: str
    content: str
    structured_data: dict[str, Any]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: float
    raw_confidence: float
    calibrated_confidence: float
    invocation_record: dict[str, Any] = field(default_factory=dict)


class ModelGateway:
    """Single boundary for every LLM invocation across all tiers and agents."""

    def __init__(self, provider: BaseLLMProvider | None = None) -> None:
        self.settings = get_settings()
        self.provider = provider or resolve_provider()
        self.breakers = get_circuit_breaker_registry()
        self.cancellations = get_cancellation_registry()

    def model_for_tier(self, tier: int) -> str:
        if tier <= 0:
            return "deterministic-tier0"
        if self.provider.provider_name == "lmstudio":
            return self.settings.lm_studio_chat_model
        if tier == 1:
            return self.settings.tier1_model
        if tier == 2:
            return self.settings.tier2_model
        return self.settings.tier3_model

    async def invoke(
        self,
        *,
        workflow_id: str,
        agent_name: str,
        tier: int,
        task_kind: str,
        system_prompt: str,
        user_prompt: str,
        budget: WorkflowBudgetTracker,
        context_payload: dict[str, Any] | None = None,
        model_override: str | None = None,
    ) -> ModelCallResult:
        """Execute a budgeted, circuit-broken, calibrated LLM call."""
        self.cancellations.check(workflow_id)
        model_key = model_override or self.model_for_tier(tier)

        # Shared token-budget context limiter at the LLM boundary
        bounded_user_prompt = fit_context(user_prompt, max_tokens=self.settings.max_context_tokens)
        est_prompt_tokens = estimate_tokens(system_prompt) + estimate_tokens(bounded_user_prompt)
        est_completion_tokens = 200 if tier <= 2 else 450
        est_cost = compute_cost_usd(
            model_key,
            prompt_tokens=est_prompt_tokens,
            completion_tokens=est_completion_tokens,
        )

        budget.check_token_and_cost_allowance(
            projected_tokens=est_prompt_tokens + est_completion_tokens,
            projected_cost_usd=est_cost,
        )

        breaker_key = f"{self.provider.provider_name}:tier{tier}"
        breaker = self.breakers.get(breaker_key)
        breaker.allow_request()

        t0 = time.perf_counter()
        try:
            resp = await self.provider.generate(
                model_key=model_key,
                tier=tier,
                task_kind=task_kind,
                system_prompt=system_prompt,
                user_prompt=bounded_user_prompt,
                context_payload=context_payload,
            )
            breaker.record_success()
        except Exception:
            breaker.record_failure()
            raise

        measured_ms = (time.perf_counter() - t0) * 1000.0
        latency_ms = round(resp.simulated_latency_ms or measured_ms, 2)
        total_tokens = resp.prompt_tokens + resp.completion_tokens
        cost_usd = compute_cost_usd(
            model_key,
            prompt_tokens=resp.prompt_tokens,
            completion_tokens=resp.completion_tokens,
        )

        # Re-check actual token usage against workflow ceiling before committing
        budget.check_token_and_cost_allowance(
            projected_tokens=total_tokens,
            projected_cost_usd=cost_usd,
        )
        budget.commit_usage(tokens=total_tokens, cost_usd=cost_usd)

        slope, intercept = MODEL_CALIBRATION_PARAMS.get(model_key, (0.92, 0.04))
        cal_conf = calibrate_confidence(resp.raw_confidence, slope=slope, intercept=intercept)

        TOKENS_TOTAL.labels(tier=str(tier), model=model_key, direction="prompt").inc(
            resp.prompt_tokens
        )
        TOKENS_TOTAL.labels(tier=str(tier), model=model_key, direction="completion").inc(
            resp.completion_tokens
        )
        COST_USD_TOTAL.labels(tier=str(tier), model=model_key).inc(cost_usd)

        invocation_record = {
            "agent_name": agent_name,
            "model_key": model_key,
            "provider": self.provider.provider_name,
            "tier": tier,
            "prompt_tokens": resp.prompt_tokens,
            "completion_tokens": resp.completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": cost_usd,
            "latency_ms": latency_ms,
            "raw_confidence": round(resp.raw_confidence, 4),
            "calibrated_confidence": cal_conf,
            "cache_hit": False,
            "status": "success",
            "error_code": None,
        }

        return ModelCallResult(
            model_key=model_key,
            provider=self.provider.provider_name,
            tier=tier,
            agent_name=agent_name,
            content=resp.content,
            structured_data=resp.structured_data,
            prompt_tokens=resp.prompt_tokens,
            completion_tokens=resp.completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            raw_confidence=round(resp.raw_confidence, 4),
            calibrated_confidence=cal_conf,
            invocation_record=invocation_record,
        )
