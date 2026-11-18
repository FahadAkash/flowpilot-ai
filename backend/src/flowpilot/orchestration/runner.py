"""Orchestrator service coordinating LangGraph execution, guardrails, DB state, and telemetry."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flowpilot.config import get_settings
from flowpilot.db.models import (
    BudgetPolicy,
    ModelInvocation,
    ToolInvocation,
    Workflow,
    WorkflowMetric,
    WorkflowStep,
    new_uuid,
)
from flowpilot.documents.chunker import estimate_tokens
from flowpilot.documents.repository import DocumentRepository
from flowpilot.guardrails.budget import BudgetLimits, WorkflowBudgetTracker
from flowpilot.guardrails.cache import get_tier0_cache
from flowpilot.guardrails.cancellation import get_cancellation_registry
from flowpilot.guardrails.exceptions import GuardrailViolationError, WorkflowTimeoutError
from flowpilot.guardrails.idempotency import find_existing_idempotent_workflow
from flowpilot.llm.gateway import ModelGateway, compute_cost_usd
from flowpilot.observability.logging import get_logger
from flowpilot.observability.metrics import (
    ACTIVE_WORKFLOWS,
    ESTIMATED_SAVINGS_USD_TOTAL,
    WORKFLOW_LATENCY_SECONDS,
    WORKFLOWS_TOTAL,
)
from flowpilot.orchestration.graph import GraphRuntimeDeps, build_flowpilot_graph

logger = get_logger("flowpilot.orchestrator")


def estimate_monolithic_baseline(documents: list[dict[str, Any]], query: str) -> tuple[int, float]:
    """Estimate token & USD cost if this request had gone directly to the Tier 3 frontier model."""
    doc_tokens = sum(estimate_tokens(str(d.get("raw_text", ""))) for d in documents)
    prompt_tokens = max(1400, doc_tokens + estimate_tokens(query) + 450)
    completion_tokens = 520
    settings = get_settings()
    cost = compute_cost_usd(
        settings.tier3_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    return prompt_tokens + completion_tokens, cost


class WorkflowOrchestratorService:
    """Service boundary executing workflows with full persistence and guardrail enforcement."""

    def __init__(self, session: AsyncSession, gateway: ModelGateway | None = None) -> None:
        self.session = session
        self.settings = get_settings()
        self.gateway = gateway or ModelGateway()
        self.doc_repo = DocumentRepository(session)
        self.cache = get_tier0_cache()
        self.cancellations = get_cancellation_registry()

    async def resolve_budget_limits(
        self,
        *,
        user_id: str,
        confidence_override: float | None = None,
    ) -> BudgetLimits:
        """Resolve effective BudgetLimits merging user-scoped and global active BudgetPolicy rows."""
        res = await self.session.execute(
            select(BudgetPolicy).where(BudgetPolicy.is_active.is_(True))
        )
        policies = list(res.scalars().all())
        global_pol = next((p for p in policies if p.scope == "global"), None)
        user_pol = next((p for p in policies if p.scope == "user" and p.user_id == user_id), None)
        active = user_pol or global_pol

        if active is None:
            return BudgetLimits(
                max_steps=self.settings.max_steps,
                max_agent_calls=self.settings.max_agent_calls,
                max_tokens_per_workflow=self.settings.max_tokens_per_workflow,
                user_daily_limit_usd=self.settings.default_user_daily_budget_usd,
                global_daily_limit_usd=self.settings.global_daily_budget_usd,
                timeout_seconds=float(self.settings.execution_timeout_seconds),
                max_retries=self.settings.max_retries,
                max_tool_calls_per_agent=self.settings.max_tool_calls_per_agent,
                max_escalations=self.settings.max_escalations,
                confidence_threshold=confidence_override
                or self.settings.default_confidence_threshold,
            )

        return BudgetLimits(
            max_steps=active.max_steps,
            max_agent_calls=active.max_agent_calls,
            max_tokens_per_workflow=active.max_tokens_per_workflow,
            max_cost_per_workflow_usd=active.max_cost_per_workflow_usd,
            user_daily_limit_usd=active.daily_cost_limit_usd,
            global_daily_limit_usd=global_pol.daily_cost_limit_usd
            if global_pol
            else self.settings.global_daily_budget_usd,
            timeout_seconds=float(active.timeout_seconds),
            max_retries=active.max_retries,
            max_tool_calls_per_agent=active.max_tool_calls_per_agent,
            max_escalations=active.max_escalations,
            confidence_threshold=(
                confidence_override
                if confidence_override is not None
                else active.confidence_threshold
            ),
        )

    async def execute_workflow(
        self,
        *,
        user_id: str,
        query: str,
        document_ids: list[str],
        idempotency_key: str | None = None,
        force_tier: int | None = None,
        confidence_override: float | None = None,
        bypass_cache: bool = False,
    ) -> Workflow:
        """Execute a complete FlowPilot workflow with idempotency, caching, LangGraph, and telemetry."""
        # 1. Idempotency check
        existing = await find_existing_idempotent_workflow(
            self.session,
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            return existing

        docs = await self.doc_repo.get_documents_by_ids(user_id=user_id, document_ids=document_ids)
        serialized_docs = await self.doc_repo.serialize_documents_for_state(docs)
        resolved_doc_ids = [d.id for d in docs]
        doc_hashes = [d.sha256 for d in docs]

        baseline_tokens, baseline_cost = estimate_monolithic_baseline(serialized_docs, query)
        workflow_id = new_uuid()
        t_start = time.perf_counter()

        # 2. Tier 0 Exact/Normalized Cache check
        cache_key = self.cache.build_key(
            query=query,
            doc_hashes=doc_hashes,
            extra=f"ft={force_tier}",
        )
        if not bypass_cache and force_tier is None:
            cached = await self.cache.get(cache_key)
            if cached is not None:
                latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
                wf = Workflow(
                    id=workflow_id,
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                    query=query,
                    document_ids=resolved_doc_ids,
                    intent=str(cached.get("intent", "cached_lookup")),
                    selected_tier=0,
                    final_tier=0,
                    routing_rationale="Served directly from Tier 0 Redis/Memory deterministic cache (0 tokens).",
                    status="completed",
                    final_response_json=cached,
                    raw_confidence=1.0,
                    calibrated_confidence=1.0,
                    step_count=1,
                    agent_call_count=1,
                    tool_call_count=0,
                    total_tokens=0,
                    total_cost_usd=0.0,
                    latency_ms=latency_ms,
                    cache_hit=True,
                    completed_at=datetime.now(UTC),
                )
                self.session.add(wf)
                self.session.add(
                    WorkflowStep(
                        workflow_id=workflow_id,
                        step_index=0,
                        node_name="tier0_cache",
                        agent_name="intent_router",
                        tier=0,
                        status="completed",
                        routing_reason="Tier 0 exact cache hit bypassed all LLM calls.",
                        input_summary_json={"query": query[:120]},
                        output_summary_json={"cache_hit": True},
                        confidence=1.0,
                        latency_ms=latency_ms,
                        tokens_used=0,
                        cost_usd=0.0,
                        completed_at=datetime.now(UTC),
                    )
                )
                self.session.add(
                    WorkflowMetric(
                        workflow_id=workflow_id,
                        tier_used=0,
                        escalated=False,
                        cache_hit=True,
                        total_tokens=0,
                        estimated_baseline_tokens=baseline_tokens,
                        total_cost_usd=0.0,
                        estimated_baseline_cost_usd=baseline_cost,
                        savings_usd=baseline_cost,
                        latency_ms=latency_ms,
                        tool_calls_count=0,
                        agent_calls_count=1,
                        step_count=1,
                        succeeded=True,
                    )
                )
                await self.session.commit()
                await self.session.refresh(wf)
                WORKFLOWS_TOTAL.labels(tier="0", status="completed", intent=wf.intent).inc()
                WORKFLOW_LATENCY_SECONDS.labels(tier="0").observe(latency_ms / 1000.0)
                ESTIMATED_SAVINGS_USD_TOTAL.inc(max(0.0, baseline_cost))
                return wf

        # 3. Persist initial "running" workflow state before handoff
        limits = await self.resolve_budget_limits(
            user_id=user_id,
            confidence_override=confidence_override,
        )
        budget = WorkflowBudgetTracker(workflow_id=workflow_id, user_id=user_id, limits=limits)

        wf = Workflow(
            id=workflow_id,
            user_id=user_id,
            idempotency_key=idempotency_key,
            query=query,
            document_ids=resolved_doc_ids,
            status="running",
        )
        self.session.add(wf)
        await self.session.commit()

        ACTIVE_WORKFLOWS.inc()
        final_state: dict[str, Any] = {}
        status = "completed"
        error_json: dict[str, Any] | None = None

        try:
            budget.check_daily_budgets()
            graph = build_flowpilot_graph(
                GraphRuntimeDeps(gateway=self.gateway, budget=budget, repo=self.doc_repo)
            )
            initial_state: dict[str, Any] = {
                "workflow_id": workflow_id,
                "user_id": user_id,
                "query": query,
                "documents": serialized_docs,
                "force_tier": force_tier,
                "confidence_threshold": limits.confidence_threshold,
                "execution_trace": [],
                "model_logs": [],
                "tool_logs": [],
                "errors": [],
            }
            async with asyncio.timeout(limits.timeout_seconds):
                final_state = await graph.ainvoke(
                    initial_state,
                    config={"configurable": {"thread_id": workflow_id}},
                )
        except TimeoutError:
            err = WorkflowTimeoutError(
                f"Workflow timed out after {limits.timeout_seconds}s.",
                details={"timeout_seconds": limits.timeout_seconds},
            )
            status = "failed"
            error_json = err.to_error_dict()
        except GuardrailViolationError as exc:
            status = (
                "cancelled" if exc.guardrail_type == "workflow_cancelled" else "budget_exceeded"
            )
            error_json = exc.to_error_dict()
            logger.warning(
                "workflow_guardrail_triggered", workflow_id=workflow_id, error=error_json
            )
        except Exception as exc:
            status = "failed"
            error_json = {"error_type": type(exc).__name__, "message": str(exc)}
            logger.exception("workflow_unexpected_error", workflow_id=workflow_id)
        finally:
            ACTIVE_WORKFLOWS.dec()
            self.cancellations.clear(workflow_id)

        wall_ms = (time.perf_counter() - t_start) * 1000.0
        trace_steps: list[dict[str, Any]] = list(final_state.get("execution_trace") or [])
        model_logs: list[dict[str, Any]] = list(final_state.get("model_logs") or [])
        tool_logs: list[dict[str, Any]] = list(final_state.get("tool_logs") or [])
        # Use summed step latencies when mock simulated latency exceeds wall clock
        step_latency_sum = sum(float(s.get("latency_ms", 0.0)) for s in trace_steps)
        effective_latency_ms = round(max(wall_ms, step_latency_sum), 2)

        selected_tier = int(final_state.get("selected_tier", force_tier or 0))
        final_tier = int(final_state.get("current_tier", selected_tier))
        intent = str(final_state.get("intent", "unknown"))
        final_response = dict(final_state.get("final_response") or {})
        if error_json and not final_response:
            final_response = {
                "summary": f"Workflow stopped safely ({status}): {error_json.get('message')}",
                "error": error_json,
                "budget_snapshot": budget.snapshot(),
                "discrepancies": final_state.get("discrepancies", []),
                "citations": [],
                "skipped_agents": [],
            }

        # 4. Persist workflow state + separate workflow_steps + model_invocations + tool_invocations + metrics
        wf.intent = intent
        wf.selected_tier = selected_tier
        wf.final_tier = final_tier
        wf.routing_rationale = str(final_state.get("routing_rationale", ""))
        wf.status = status
        wf.final_response_json = final_response
        wf.raw_confidence = float(final_state.get("raw_confidence", 0.0))
        wf.calibrated_confidence = float(final_state.get("calibrated_confidence", 0.0))
        wf.escalation_count = budget.escalations
        wf.retry_count = budget.retries
        wf.step_count = budget.steps
        wf.agent_call_count = budget.agent_calls
        wf.tool_call_count = budget.total_tool_calls
        wf.total_tokens = budget.tokens
        wf.total_cost_usd = round(budget.cost_usd, 7)
        wf.latency_ms = effective_latency_ms
        wf.error_json = error_json
        wf.completed_at = datetime.now(UTC)

        step_id_by_agent: dict[str, str] = {}
        for idx, step in enumerate(trace_steps):
            step_row = WorkflowStep(
                id=new_uuid(),
                workflow_id=workflow_id,
                step_index=idx,
                node_name=str(step.get("node_name", "step")),
                agent_name=str(step.get("agent_name", "unknown")),
                tier=int(step.get("tier", final_tier)),
                status=str(step.get("status", "completed")),
                routing_reason=str(step.get("routing_reason", "")),
                input_summary_json=dict(step.get("input_summary_json") or {}),
                output_summary_json=dict(step.get("output_summary_json") or {}),
                confidence=step.get("confidence"),
                latency_ms=float(step.get("latency_ms", 0.0)),
                tokens_used=int(step.get("tokens_used", 0)),
                cost_usd=float(step.get("cost_usd", 0.0)),
                error_message=step.get("error_message"),
                completed_at=datetime.now(UTC),
            )
            self.session.add(step_row)
            step_id_by_agent[step_row.agent_name] = step_row.id

        # Ensure workflow_steps are flushed before FK-referencing model/tool invocations on Postgres
        await self.session.flush()

        for ml in model_logs:
            self.session.add(
                ModelInvocation(
                    workflow_id=workflow_id,
                    workflow_step_id=step_id_by_agent.get(str(ml.get("agent_name", ""))),
                    agent_name=str(ml.get("agent_name", "unknown")),
                    model_key=str(ml.get("model_key", "unknown")),
                    provider=str(ml.get("provider", "mock")),
                    tier=int(ml.get("tier", 1)),
                    prompt_tokens=int(ml.get("prompt_tokens", 0)),
                    completion_tokens=int(ml.get("completion_tokens", 0)),
                    total_tokens=int(ml.get("total_tokens", 0)),
                    cost_usd=float(ml.get("cost_usd", 0.0)),
                    latency_ms=float(ml.get("latency_ms", 0.0)),
                    raw_confidence=ml.get("raw_confidence"),
                    calibrated_confidence=ml.get("calibrated_confidence"),
                    cache_hit=bool(ml.get("cache_hit", False)),
                    status=str(ml.get("status", "success")),
                    error_code=ml.get("error_code"),
                )
            )

        for tl in tool_logs:
            self.session.add(
                ToolInvocation(
                    workflow_id=workflow_id,
                    workflow_step_id=step_id_by_agent.get(str(tl.get("agent_name", ""))),
                    agent_name=str(tl.get("agent_name", "unknown")),
                    tool_name=str(tl.get("tool_name", "unknown")),
                    arguments_json=dict(tl.get("arguments_json") or {}),
                    result_summary_json=dict(tl.get("result_summary_json") or {}),
                    latency_ms=float(tl.get("latency_ms", 0.0)),
                    status=str(tl.get("status", "success")),
                    error_message=tl.get("error_message"),
                )
            )

        savings_usd = round(max(0.0, baseline_cost - wf.total_cost_usd), 7)
        self.session.add(
            WorkflowMetric(
                workflow_id=workflow_id,
                tier_used=final_tier,
                escalated=budget.escalations > 0,
                cache_hit=False,
                total_tokens=wf.total_tokens,
                estimated_baseline_tokens=baseline_tokens,
                total_cost_usd=wf.total_cost_usd,
                estimated_baseline_cost_usd=baseline_cost,
                savings_usd=savings_usd,
                latency_ms=effective_latency_ms,
                tool_calls_count=wf.tool_call_count,
                agent_calls_count=wf.agent_call_count,
                step_count=wf.step_count,
                succeeded=status == "completed",
            )
        )

        await self.session.commit()
        await self.session.refresh(wf)

        if status == "completed" and final_response and not bypass_cache and force_tier is None:
            await self.cache.set(cache_key, final_response)

        WORKFLOWS_TOTAL.labels(tier=str(final_tier), status=status, intent=intent).inc()
        WORKFLOW_LATENCY_SECONDS.labels(tier=str(final_tier)).observe(effective_latency_ms / 1000.0)
        if savings_usd > 0:
            ESTIMATED_SAVINGS_USD_TOTAL.inc(savings_usd)

        return wf
