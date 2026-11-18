"""Idempotent database seeders for users, agents, models, and budget policies."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flowpilot.config import get_settings
from flowpilot.db.models import AgentConfig, BudgetPolicy, ModelRegistry, User
from flowpilot.security import hash_api_key, hash_password

DEMO_USER_EMAIL = "demo@flowpilot.ai"
DEMO_USER_PASSWORD = "flowpilot-demo-password"
DEMO_API_KEY = "fp_demo_key_local_only"

DEFAULT_MODELS: list[dict[str, object]] = [
    {
        "model_key": "deterministic-tier0",
        "provider": "deterministic",
        "tier": 0,
        "input_cost_per_1k": 0.0,
        "output_cost_per_1k": 0.0,
        "max_context_tokens": 1_000_000,
        "avg_latency_ms": 6.0,
        "calibration_slope": 1.0,
        "calibration_intercept": 0.0,
    },
    {
        "model_key": "gpt-4o-mini",
        "provider": "openai",
        "tier": 1,
        "input_cost_per_1k": 0.00015,
        "output_cost_per_1k": 0.00060,
        "max_context_tokens": 128_000,
        "avg_latency_ms": 340.0,
        "calibration_slope": 0.92,
        "calibration_intercept": 0.04,
    },
    {
        "model_key": "gemini-2.5-flash-lite",
        "provider": "gemini",
        "tier": 1,
        "input_cost_per_1k": 0.00010,
        "output_cost_per_1k": 0.00040,
        "max_context_tokens": 1_000_000,
        "avg_latency_ms": 280.0,
        "calibration_slope": 0.94,
        "calibration_intercept": 0.03,
    },
    {
        "model_key": "llama-3.1-8b-local",
        "provider": "ollama",
        "tier": 1,
        "input_cost_per_1k": 0.0,
        "output_cost_per_1k": 0.0,
        "max_context_tokens": 32_000,
        "avg_latency_ms": 420.0,
        "calibration_slope": 0.88,
        "calibration_intercept": 0.05,
    },
    {
        "model_key": "google/gemma-4-12b-qat",
        "provider": "lmstudio",
        "tier": 2,
        "input_cost_per_1k": 0.0,
        "output_cost_per_1k": 0.0,
        "max_context_tokens": 128_000,
        "avg_latency_ms": 850.0,
        "calibration_slope": 0.94,
        "calibration_intercept": 0.03,
    },
    {
        "model_key": "gpt-4o",
        "provider": "openai",
        "tier": 3,
        "input_cost_per_1k": 0.00250,
        "output_cost_per_1k": 0.01000,
        "max_context_tokens": 128_000,
        "avg_latency_ms": 1450.0,
        "calibration_slope": 0.97,
        "calibration_intercept": 0.01,
    },
    {
        "model_key": "claude-3-7-sonnet",
        "provider": "anthropic",
        "tier": 3,
        "input_cost_per_1k": 0.00300,
        "output_cost_per_1k": 0.01500,
        "max_context_tokens": 200_000,
        "avg_latency_ms": 1620.0,
        "calibration_slope": 0.98,
        "calibration_intercept": 0.01,
    },
    {
        "model_key": "gemini-2.5-pro",
        "provider": "gemini",
        "tier": 3,
        "input_cost_per_1k": 0.00125,
        "output_cost_per_1k": 0.01000,
        "max_context_tokens": 1_000_000,
        "avg_latency_ms": 1380.0,
        "calibration_slope": 0.96,
        "calibration_intercept": 0.02,
    },
]

DEFAULT_AGENTS: list[dict[str, object]] = [
    {
        "name": "intent_router",
        "role": "Classifies user intent, complexity signals, and selects the cheapest viable execution tier.",
        "default_tier": 0,
        "default_model_key": "gpt-4o-mini",
        "max_tool_calls": 2,
    },
    {
        "name": "planner",
        "role": "Decomposes multi-document tasks into the minimal ordered set of specialist steps.",
        "default_tier": 2,
        "default_model_key": "gpt-4o-mini",
        "max_tool_calls": 2,
    },
    {
        "name": "retrieval",
        "role": "Retrieves high-signal document chunks via hybrid pgvector + lexical search.",
        "default_tier": 2,
        "default_model_key": "deterministic-tier0",
        "max_tool_calls": 5,
    },
    {
        "name": "extraction",
        "role": "Extracts structured typed fields (invoices, POs, policies, contract clauses) with page citations.",
        "default_tier": 1,
        "default_model_key": "gpt-4o-mini",
        "max_tool_calls": 5,
    },
    {
        "name": "validation",
        "role": "Validates outputs against Pydantic schemas, arithmetic invariants, and calibrated confidence thresholds.",
        "default_tier": 0,
        "default_model_key": "deterministic-tier0",
        "max_tool_calls": 3,
    },
    {
        "name": "comparison",
        "role": "Performs 2-way and 3-way document comparison to detect discrepancies and policy concerns.",
        "default_tier": 2,
        "default_model_key": "gpt-4o-mini",
        "max_tool_calls": 5,
    },
    {
        "name": "reasoning",
        "role": "Tier 3 frontier escalation agent for ambiguous legal/policy conflicts and low-confidence resolution.",
        "default_tier": 3,
        "default_model_key": "gpt-4o",
        "max_tool_calls": 3,
    },
    {
        "name": "response",
        "role": "Synthesizes the final grounded structured report with citations and routing justification.",
        "default_tier": 0,
        "default_model_key": "deterministic-tier0",
        "max_tool_calls": 1,
    },
]


async def seed_defaults(session: AsyncSession) -> User:
    """Idempotently populate default models, agents, policies, and demo user."""
    settings = get_settings()

    user_res = await session.execute(select(User).where(User.email == DEMO_USER_EMAIL))
    demo_user = user_res.scalar_one_or_none()
    if demo_user is None:
        demo_user = User(
            email=DEMO_USER_EMAIL,
            full_name="FlowPilot Enterprise Admin",
            hashed_password=hash_password(DEMO_USER_PASSWORD),
            role="admin",
            api_key_hash=hash_api_key(DEMO_API_KEY),
            is_active=True,
        )
        session.add(demo_user)
        await session.flush()

    for m in DEFAULT_MODELS:
        exists = await session.execute(
            select(ModelRegistry).where(ModelRegistry.model_key == m["model_key"])
        )
        if exists.scalar_one_or_none() is None:
            session.add(ModelRegistry(**m))

    for a in DEFAULT_AGENTS:
        exists = await session.execute(select(AgentConfig).where(AgentConfig.name == a["name"]))
        if exists.scalar_one_or_none() is None:
            session.add(AgentConfig(**a))

    default_policies: list[dict[str, object]] = [
        {
            "name": "global-default",
            "scope": "global",
            "user_id": None,
            "task_type": None,
            "max_steps": settings.max_steps,
            "max_agent_calls": settings.max_agent_calls,
            "max_tokens_per_workflow": settings.max_tokens_per_workflow,
            "max_cost_per_workflow_usd": 0.50,
            "daily_cost_limit_usd": settings.global_daily_budget_usd,
            "timeout_seconds": settings.execution_timeout_seconds,
            "max_retries": settings.max_retries,
            "max_tool_calls_per_agent": settings.max_tool_calls_per_agent,
            "max_escalations": settings.max_escalations,
            "confidence_threshold": settings.default_confidence_threshold,
        },
        {
            "name": "legal-high-assurance",
            "scope": "task_type",
            "user_id": None,
            "task_type": "legal_reasoning",
            "max_steps": 12,
            "max_agent_calls": 15,
            "max_tokens_per_workflow": 12_000,
            "max_cost_per_workflow_usd": 0.75,
            "daily_cost_limit_usd": settings.global_daily_budget_usd,
            "timeout_seconds": 60,
            "max_retries": 2,
            "max_tool_calls_per_agent": 5,
            "max_escalations": 1,
            "confidence_threshold": 0.88,
        },
        {
            "name": "demo-user-policy",
            "scope": "user",
            "user_id": demo_user.id,
            "task_type": None,
            "max_steps": settings.max_steps,
            "max_agent_calls": settings.max_agent_calls,
            "max_tokens_per_workflow": settings.max_tokens_per_workflow,
            "max_cost_per_workflow_usd": 0.50,
            "daily_cost_limit_usd": settings.default_user_daily_budget_usd,
            "timeout_seconds": settings.execution_timeout_seconds,
            "max_retries": settings.max_retries,
            "max_tool_calls_per_agent": settings.max_tool_calls_per_agent,
            "max_escalations": settings.max_escalations,
            "confidence_threshold": settings.default_confidence_threshold,
        },
    ]

    for p in default_policies:
        exists = await session.execute(select(BudgetPolicy).where(BudgetPolicy.name == p["name"]))
        if exists.scalar_one_or_none() is None:
            session.add(BudgetPolicy(**p))

    await session.commit()
    return demo_user
