"""Cost analytics, tier routing telemetry, model registry, and agent registry routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from flowpilot.api.deps import CurrentUserDep, SessionDep
from flowpilot.benchmarks.evaluator import percentile
from flowpilot.db.models import (
    AgentConfig,
    ModelInvocation,
    ModelRegistry,
    Workflow,
    WorkflowMetric,
)

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/overview")
async def analytics_overview(user: CurrentUserDep, session: SessionDep) -> dict[str, Any]:
    wf_rows = list(
        (await session.execute(select(Workflow).where(Workflow.user_id == user.id))).scalars().all()
    )
    wf_ids = [w.id for w in wf_rows]
    metrics_rows = (
        list(
            (
                await session.execute(
                    select(WorkflowMetric).where(WorkflowMetric.workflow_id.in_(wf_ids))
                )
            )
            .scalars()
            .all()
        )
        if wf_ids
        else []
    )
    inv_rows = (
        list(
            (
                await session.execute(
                    select(ModelInvocation).where(ModelInvocation.workflow_id.in_(wf_ids))
                )
            )
            .scalars()
            .all()
        )
        if wf_ids
        else []
    )

    total_workflows = len(wf_rows)
    total_tokens = sum(w.total_tokens for w in wf_rows)
    total_cost = round(sum(w.total_cost_usd for w in wf_rows), 6)
    baseline_tokens = sum(m.estimated_baseline_tokens for m in metrics_rows)
    baseline_cost = round(sum(m.estimated_baseline_cost_usd for m in metrics_rows), 6)
    savings_usd = round(sum(m.savings_usd for m in metrics_rows), 6)
    latencies = [w.latency_ms for w in wf_rows]
    escalated_count = sum(1 for w in wf_rows if w.escalation_count > 0)
    cache_hits = sum(1 for w in wf_rows if w.cache_hit)

    tier_counts = {"tier_0": 0, "tier_1": 0, "tier_2": 0, "tier_3": 0}
    tier_latencies: dict[str, list[float]] = {
        "tier_0": [],
        "tier_1": [],
        "tier_2": [],
        "tier_3": [],
    }
    for w in wf_rows:
        k = f"tier_{max(0, min(3, w.final_tier))}"
        tier_counts[k] += 1
        tier_latencies[k].append(w.latency_ms)

    latency_by_tier = [
        {
            "tier": f"Tier {i}",
            "count": tier_counts[f"tier_{i}"],
            "p50_ms": percentile(tier_latencies[f"tier_{i}"], 50),
            "p95_ms": percentile(tier_latencies[f"tier_{i}"], 95),
        }
        for i in range(4)
    ]

    agent_cost: dict[str, dict[str, Any]] = {}
    for inv in inv_rows:
        bucket = agent_cost.setdefault(
            inv.agent_name,
            {"agent": inv.agent_name, "calls": 0, "tokens": 0, "cost_usd": 0.0},
        )
        bucket["calls"] += 1
        bucket["tokens"] += inv.total_tokens
        bucket["cost_usd"] = round(bucket["cost_usd"] + inv.cost_usd, 6)

    token_savings_pct = (
        round((1.0 - total_tokens / baseline_tokens) * 100.0, 2) if baseline_tokens > 0 else 0.0
    )
    cost_savings_pct = (
        round((1.0 - total_cost / baseline_cost) * 100.0, 2) if baseline_cost > 0 else 0.0
    )

    return {
        "total_workflows": total_workflows,
        "total_tokens": total_tokens,
        "estimated_baseline_tokens": baseline_tokens,
        "token_savings_pct": token_savings_pct,
        "total_cost_usd": total_cost,
        "estimated_baseline_cost_usd": baseline_cost,
        "savings_usd": savings_usd,
        "cost_savings_pct": cost_savings_pct,
        "p50_latency_ms": percentile(latencies, 50),
        "p95_latency_ms": percentile(latencies, 95),
        "escalation_rate_pct": round((escalated_count / max(1, total_workflows)) * 100.0, 2),
        "cache_hit_rate_pct": round((cache_hits / max(1, total_workflows)) * 100.0, 2),
        "tier_distribution": tier_counts,
        "latency_by_tier": latency_by_tier,
        "agent_cost_breakdown": list(agent_cost.values()),
    }


@router.get("/models")
async def list_model_registry(_user: CurrentUserDep, session: SessionDep) -> list[dict[str, Any]]:
    rows = list(
        (await session.execute(select(ModelRegistry).order_by(ModelRegistry.tier))).scalars().all()
    )
    return [
        {
            "id": r.id,
            "model_key": r.model_key,
            "provider": r.provider,
            "tier": r.tier,
            "input_cost_per_1k": r.input_cost_per_1k,
            "output_cost_per_1k": r.output_cost_per_1k,
            "max_context_tokens": r.max_context_tokens,
            "avg_latency_ms": r.avg_latency_ms,
            "calibration_slope": r.calibration_slope,
            "calibration_intercept": r.calibration_intercept,
            "is_active": r.is_active,
        }
        for r in rows
    ]


@router.get("/agents")
async def list_agents(_user: CurrentUserDep, session: SessionDep) -> list[dict[str, Any]]:
    rows = list(
        (await session.execute(select(AgentConfig).order_by(AgentConfig.default_tier)))
        .scalars()
        .all()
    )
    return [
        {
            "id": r.id,
            "name": r.name,
            "role": r.role,
            "default_tier": r.default_tier,
            "default_model_key": r.default_model_key,
            "max_tool_calls": r.max_tool_calls,
            "prompt_version": r.prompt_version,
            "is_enabled": r.is_enabled,
        }
        for r in rows
    ]
