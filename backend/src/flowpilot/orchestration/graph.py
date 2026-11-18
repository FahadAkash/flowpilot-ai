"""LangGraph StateGraph assembly for FlowPilot AI Tier 0-3 Multi-Agent Orchestration.

Follows mastering-langgraph-agent-skill guidelines:
- Single-purpose nodes with raw FlowPilotState
- Explicit conditional routing via `add_conditional_edges`
- Append-only reducers (`operator.add`) for traces and invocation logs
- Compiled with `InMemorySaver()` checkpointer keyed by `thread_id=workflow_id`
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from flowpilot.documents.repository import DocumentRepository
from flowpilot.guardrails.budget import WorkflowBudgetTracker
from flowpilot.guardrails.cancellation import get_cancellation_registry
from flowpilot.llm.gateway import ModelGateway
from flowpilot.orchestration.agents.comparison import run_comparison_agent
from flowpilot.orchestration.agents.extraction import run_extraction_agent
from flowpilot.orchestration.agents.planner import run_planner_agent
from flowpilot.orchestration.agents.reasoning import run_reasoning_agent_tier3
from flowpilot.orchestration.agents.response import run_response_agent
from flowpilot.orchestration.agents.retrieval import run_retrieval_agent
from flowpilot.orchestration.agents.tier1_agent import run_tier1_lightweight
from flowpilot.orchestration.agents.validation import run_validation_agent
from flowpilot.orchestration.router import route_intent
from flowpilot.orchestration.state import FlowPilotState
from flowpilot.orchestration.tier0 import try_tier0_fast_path


@dataclass(slots=True)
class GraphRuntimeDeps:
    gateway: ModelGateway
    budget: WorkflowBudgetTracker
    repo: DocumentRepository | None = None


def build_flowpilot_graph(deps: GraphRuntimeDeps) -> Any:
    """Build and compile the FlowPilot AI LangGraph StateGraph."""
    cancellations = get_cancellation_registry()

    def _guard_node(state: FlowPilotState, node_name: str) -> None:
        cancellations.check(str(state["workflow_id"]))
        deps.budget.record_step(node_name)

    async def intent_router_node(state: FlowPilotState) -> dict[str, Any]:
        _guard_node(state, "intent_router")
        t0 = time.perf_counter()
        deps.budget.record_agent_call("intent_router")
        decision = await route_intent(
            workflow_id=str(state["workflow_id"]),
            query=str(state["query"]),
            documents=list(state.get("documents") or []),
            gateway=deps.gateway,
            budget=deps.budget,
            force_tier=state.get("force_tier"),
        )
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        step_entry = {
            "node_name": "intent_router",
            "agent_name": "intent_router",
            "tier": decision.selected_tier,
            "status": "completed",
            "routing_reason": decision.rationale,
            "input_summary_json": {
                "query": str(state["query"])[:120],
                "docs": len(state.get("documents") or []),
            },
            "output_summary_json": {
                "intent": decision.intent,
                "selected_tier": decision.selected_tier,
            },
            "confidence": decision.calibrated_confidence,
            "latency_ms": decision.latency_ms or latency_ms,
            "tokens_used": int(decision.model_log["total_tokens"]) if decision.model_log else 0,
            "cost_usd": float(decision.model_log["cost_usd"]) if decision.model_log else 0.0,
        }
        update: dict[str, Any] = {
            "intent": decision.intent,
            "selected_tier": decision.selected_tier,
            "current_tier": decision.selected_tier,
            "routing_rationale": decision.rationale,
            "raw_confidence": decision.raw_confidence,
            "calibrated_confidence": decision.calibrated_confidence,
            "execution_trace": [step_entry],
        }
        if decision.tier0_preview is not None:
            update["tier0_output"] = decision.tier0_preview
            update["tier0_handled"] = True
        if decision.model_log is not None:
            update["model_logs"] = [decision.model_log]
        return update

    async def tier0_fast_path_node(state: FlowPilotState) -> dict[str, Any]:
        _guard_node(state, "tier0_fast_path")
        t0 = time.perf_counter()
        deps.budget.record_agent_call("extraction")
        deps.budget.record_tool_call("extraction", "tier0_deterministic_extractor")

        preview = state.get("tier0_output")
        if preview and preview.get("answer"):
            res_dict = dict(preview)
            handled = True
        else:
            res = try_tier0_fast_path(str(state["query"]), list(state.get("documents") or []))
            handled = res.handled
            res_dict = {
                "answer": res.answer,
                "extracted_fields": res.extracted_fields,
                "citations": res.citations,
                "matched_rule": res.matched_rule,
            }

        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        tool_log = {
            "agent_name": "extraction",
            "tool_name": "tier0_deterministic_extractor",
            "arguments_json": {"query": str(state["query"])[:100]},
            "result_summary_json": {"handled": handled, "rule": res_dict.get("matched_rule", "")},
            "latency_ms": latency_ms,
            "status": "success" if handled else "fallback",
            "error_message": None,
        }
        step_entry = {
            "node_name": "tier0_fast_path",
            "agent_name": "extraction",
            "tier": 0,
            "status": "completed" if handled else "fallback",
            "routing_reason": (
                f"Zero-LLM deterministic rule '{res_dict.get('matched_rule')}' resolved query."
                if handled
                else "Deterministic rules did not match cleanly; falling back to Tier 1 Lightweight AI."
            ),
            "input_summary_json": {"query": str(state["query"])[:100]},
            "output_summary_json": {
                "handled": handled,
                "fields": list((res_dict.get("extracted_fields") or {}).keys()),
            },
            "confidence": 1.0 if handled else 0.0,
            "latency_ms": latency_ms,
            "tokens_used": 0,
            "cost_usd": 0.0,
        }
        return {
            "tier0_handled": handled,
            "tier0_output": res_dict if handled else {},
            "current_tier": 0 if handled else 1,
            "raw_confidence": 1.0 if handled else 0.5,
            "calibrated_confidence": 1.0 if handled else 0.5,
            "tool_logs": [tool_log],
            "execution_trace": [step_entry],
        }

    async def tier1_lightweight_node(state: FlowPilotState) -> dict[str, Any]:
        _guard_node(state, "tier1_lightweight")
        t0 = time.perf_counter()
        out = await run_tier1_lightweight(
            workflow_id=str(state["workflow_id"]),
            query=str(state["query"]),
            intent=str(state.get("intent", "document_extraction")),
            documents=list(state.get("documents") or []),
            gateway=deps.gateway,
            budget=deps.budget,
        )
        latency_ms = round(
            (time.perf_counter() - t0) * 1000.0 + float(out["model_log"]["latency_ms"]), 2
        )
        step_entry = {
            "node_name": "tier1_lightweight",
            "agent_name": "extraction",
            "tier": 1,
            "status": "completed",
            "routing_reason": f"Tier 1 Lightweight AI executed intent '{state.get('intent')}'.",
            "input_summary_json": {"doc_count": len(state.get("documents") or [])},
            "output_summary_json": {
                "doc_type": out["doc_type"],
                "records": len(out["extracted_records"]),
            },
            "confidence": out["calibrated_confidence"],
            "latency_ms": latency_ms,
            "tokens_used": int(out["model_log"]["total_tokens"]),
            "cost_usd": float(out["model_log"]["cost_usd"]),
        }
        return {
            "current_tier": 1,
            "tier1_output": {"answer": out["answer"], "doc_type": out["doc_type"]},
            "extracted_records": out["extracted_records"],
            "raw_confidence": out["raw_confidence"],
            "calibrated_confidence": out["calibrated_confidence"],
            "model_logs": [out["model_log"]],
            "execution_trace": [step_entry],
        }

    async def planner_node(state: FlowPilotState) -> dict[str, Any]:
        _guard_node(state, "planner")
        t0 = time.perf_counter()
        out = await run_planner_agent(
            workflow_id=str(state["workflow_id"]),
            query=str(state["query"]),
            intent=str(state.get("intent", "multi_doc_comparison")),
            documents=list(state.get("documents") or []),
            gateway=deps.gateway,
            budget=deps.budget,
        )
        model_log = out.get("model_log")
        latency_ms = round(
            (time.perf_counter() - t0) * 1000.0 + float(out.get("latency_ms", 0.0)), 2
        )
        step_entry = {
            "node_name": "planner",
            "agent_name": "planner",
            "tier": 2,
            "status": "completed",
            "routing_reason": f"Planned minimal specialist sequence: {' -> '.join(out['plan_steps'])}.",
            "input_summary_json": {"intent": state.get("intent")},
            "output_summary_json": {"plan_steps": out["plan_steps"]},
            "confidence": out["calibrated_confidence"],
            "latency_ms": latency_ms,
            "tokens_used": int(model_log["total_tokens"]) if model_log else 0,
            "cost_usd": float(model_log["cost_usd"]) if model_log else 0.0,
        }
        res: dict[str, Any] = {
            "current_tier": max(2, int(state.get("current_tier", 2))),
            "plan_steps": out["plan_steps"],
            "execution_trace": [step_entry],
        }
        if model_log:
            res["model_logs"] = [model_log]
        return res

    async def retrieval_node(state: FlowPilotState) -> dict[str, Any]:
        _guard_node(state, "retrieval")
        t0 = time.perf_counter()
        out = await run_retrieval_agent(
            query=str(state["query"]),
            documents=list(state.get("documents") or []),
            repo=deps.repo,
            budget=deps.budget,
        )
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        step_entry = {
            "node_name": "retrieval",
            "agent_name": "retrieval",
            "tier": 2,
            "status": "completed",
            "routing_reason": f"Retrieved {len(out['retrieved_chunks'])} hybrid vector+lexical chunks.",
            "input_summary_json": {"doc_count": len(state.get("documents") or [])},
            "output_summary_json": {"chunks": len(out["retrieved_chunks"])},
            "confidence": 1.0,
            "latency_ms": latency_ms,
            "tokens_used": 0,
            "cost_usd": 0.0,
        }
        return {
            "retrieved_chunks": out["retrieved_chunks"],
            "tool_logs": out["tool_logs"],
            "execution_trace": [step_entry],
        }

    async def extraction_node(state: FlowPilotState) -> dict[str, Any]:
        _guard_node(state, "extraction")
        t0 = time.perf_counter()
        retry_feedback = None
        if state.get("needs_retry"):
            deps.budget.record_retry("Validation requested structured extraction retry.")
            val_rep = state.get("validation_report") or {}
            retry_feedback = f"Fix failed validation rules: {val_rep.get('failed_rules', [])}"

        out = await run_extraction_agent(
            workflow_id=str(state["workflow_id"]),
            query=str(state["query"]),
            documents=list(state.get("documents") or []),
            retrieved_chunks=list(state.get("retrieved_chunks") or []),
            gateway=deps.gateway,
            budget=deps.budget,
            retry_feedback=retry_feedback,
        )
        model_log = out.get("model_log")
        latency_ms = round(
            (time.perf_counter() - t0) * 1000.0
            + (float(model_log["latency_ms"]) if model_log else 0.0),
            2,
        )
        step_entry = {
            "node_name": "extraction",
            "agent_name": "extraction",
            "tier": 2,
            "status": "completed",
            "routing_reason": (
                "Deterministic structured parser achieved full schema coverage (0 LLM tokens)."
                if model_log is None
                else "Extracted typed Pydantic document records with Tier 2 LLM assistance."
            ),
            "input_summary_json": {
                "chunks": len(state.get("retrieved_chunks") or []),
                "retry": bool(retry_feedback),
            },
            "output_summary_json": {"records_extracted": len(out["extracted_records"])},
            "confidence": out["calibrated_confidence"],
            "latency_ms": latency_ms,
            "tokens_used": int(model_log["total_tokens"]) if model_log else 0,
            "cost_usd": float(model_log["cost_usd"]) if model_log else 0.0,
        }
        res: dict[str, Any] = {
            "extracted_records": out["extracted_records"],
            "raw_confidence": out["raw_confidence"],
            "calibrated_confidence": out["calibrated_confidence"],
            "needs_retry": False,
            "retry_count": deps.budget.retries,
            "tool_logs": out["tool_logs"],
            "execution_trace": [step_entry],
        }
        if model_log:
            res["model_logs"] = [model_log]
        return res

    async def comparison_node(state: FlowPilotState) -> dict[str, Any]:
        _guard_node(state, "comparison")
        t0 = time.perf_counter()
        out = await run_comparison_agent(
            workflow_id=str(state["workflow_id"]),
            query=str(state["query"]),
            extracted_records=list(state.get("extracted_records") or []),
            gateway=deps.gateway,
            budget=deps.budget,
        )
        model_log = out.get("model_log")
        latency_ms = round(
            (time.perf_counter() - t0) * 1000.0
            + (float(model_log["latency_ms"]) if model_log else 0.0),
            2,
        )
        step_entry = {
            "node_name": "comparison",
            "agent_name": "comparison",
            "tier": 2,
            "status": "completed",
            "routing_reason": (
                f"Cross-document comparison detected {len(out['discrepancies'])} discrepancy/concern item(s)."
            ),
            "input_summary_json": {"records": len(state.get("extracted_records") or [])},
            "output_summary_json": {"discrepancies": len(out["discrepancies"])},
            "confidence": out["calibrated_confidence"],
            "latency_ms": latency_ms,
            "tokens_used": int(model_log["total_tokens"]) if model_log else 0,
            "cost_usd": float(model_log["cost_usd"]) if model_log else 0.0,
        }
        res: dict[str, Any] = {
            "discrepancies": out["discrepancies"],
            "raw_confidence": out["raw_confidence"],
            "calibrated_confidence": out["calibrated_confidence"],
            "tool_logs": out["tool_logs"],
            "execution_trace": [step_entry],
        }
        if model_log:
            res["model_logs"] = [model_log]
        return res

    async def validation_node(state: FlowPilotState) -> dict[str, Any]:
        _guard_node(state, "validation")
        t0 = time.perf_counter()
        current_tier = int(state.get("current_tier", 0))
        force_t3 = state.get("force_tier") == 3 and current_tier < 3
        report = await run_validation_agent(
            intent=str(state.get("intent", "unknown")),
            current_tier=current_tier,
            extracted_records=list(state.get("extracted_records") or []),
            discrepancies=list(state.get("discrepancies") or []),
            tier0_output=state.get("tier0_output"),
            calibrated_confidence=float(state.get("calibrated_confidence", 0.0)),
            confidence_threshold=float(
                state.get("confidence_threshold", deps.budget.limits.confidence_threshold)
            ),
            budget=deps.budget,
        )
        if force_t3 and deps.budget.can_escalate():
            report.needs_escalation = True
            report.escalation_reason = (
                "Explicitly escalated to Tier 3 frontier model via force_tier=3."
            )

        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        step_entry = {
            "node_name": "validation",
            "agent_name": "validation",
            "tier": current_tier,
            "status": "completed",
            "routing_reason": (
                f"Evaluated {report.rules_evaluated} validation rule(s); "
                + (
                    f"triggering Tier 3 escalation ({report.escalation_reason})."
                    if report.needs_escalation
                    else ("requesting retry." if report.needs_retry else "validation passed.")
                )
            ),
            "input_summary_json": {"calibrated_confidence": state.get("calibrated_confidence")},
            "output_summary_json": report.model_dump(),
            "confidence": float(state.get("calibrated_confidence", 0.0)),
            "latency_ms": latency_ms,
            "tokens_used": 0,
            "cost_usd": 0.0,
        }
        return {
            "validation_report": report.model_dump(),
            "needs_retry": report.needs_retry,
            "needs_escalation": report.needs_escalation,
            "escalation_reason": report.escalation_reason,
            "execution_trace": [step_entry],
        }

    async def reasoning_tier3_node(state: FlowPilotState) -> dict[str, Any]:
        _guard_node(state, "reasoning_tier3")
        t0 = time.perf_counter()
        from_tier = int(state.get("current_tier", 2))
        reason = str(
            state.get("escalation_reason") or "Complex multi-document conflict requires Tier 3."
        )
        out = await run_reasoning_agent_tier3(
            workflow_id=str(state["workflow_id"]),
            query=str(state["query"]),
            from_tier=from_tier,
            escalation_reason=reason,
            extracted_records=list(state.get("extracted_records") or []),
            discrepancies=list(state.get("discrepancies") or []),
            gateway=deps.gateway,
            budget=deps.budget,
        )
        latency_ms = round(
            (time.perf_counter() - t0) * 1000.0 + float(out["model_log"]["latency_ms"]), 2
        )
        step_entry = {
            "node_name": "reasoning_tier3",
            "agent_name": "reasoning",
            "tier": 3,
            "status": "completed",
            "routing_reason": f"Tier 3 Frontier Escalation executed: {reason}",
            "input_summary_json": {
                "from_tier": from_tier,
                "discrepancies": len(state.get("discrepancies") or []),
            },
            "output_summary_json": {
                "resolutions": len(out["reasoning_output"].get("resolutions", [])),
                "calibrated_confidence": out["calibrated_confidence"],
            },
            "confidence": out["calibrated_confidence"],
            "latency_ms": latency_ms,
            "tokens_used": int(out["model_log"]["total_tokens"]),
            "cost_usd": float(out["model_log"]["cost_usd"]),
        }
        return {
            "current_tier": 3,
            "reasoning_output": out["reasoning_output"],
            "raw_confidence": out["raw_confidence"],
            "calibrated_confidence": out["calibrated_confidence"],
            "needs_escalation": False,
            "escalation_count": deps.budget.escalations,
            "model_logs": [out["model_log"]],
            "execution_trace": [step_entry],
        }

    async def response_node(state: FlowPilotState) -> dict[str, Any]:
        _guard_node(state, "response")
        t0 = time.perf_counter()
        final_resp = await run_response_agent(state=dict(state), budget=deps.budget)
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        step_entry = {
            "node_name": "response",
            "agent_name": "response",
            "tier": int(state.get("current_tier", 0)),
            "status": "completed",
            "routing_reason": (
                f"Synthesized final Tier {final_resp['final_tier']} response "
                f"(skipped {len(final_resp['skipped_agents'])} unnecessary agent(s))."
            ),
            "input_summary_json": {"discrepancies": len(final_resp["discrepancies"])},
            "output_summary_json": {"citations": len(final_resp["citations"])},
            "confidence": float(state.get("calibrated_confidence", 0.0)),
            "latency_ms": latency_ms,
            "tokens_used": 0,
            "cost_usd": 0.0,
        }
        return {
            "final_response": final_resp,
            "execution_trace": [step_entry],
        }

    # Explicit conditional routing functions (never hidden inside nodes)
    def route_after_intent(state: FlowPilotState) -> str:
        tier = int(state.get("selected_tier", 1))
        if tier == 0:
            return "tier0_fast_path"
        if tier == 1:
            return "tier1_lightweight"
        return "planner"

    def route_after_tier0(state: FlowPilotState) -> str:
        return "validation" if state.get("tier0_handled") else "tier1_lightweight"

    def route_after_extraction(state: FlowPilotState) -> str:
        plan = list(state.get("plan_steps") or [])
        if "comparison" in plan or len(state.get("documents") or []) >= 2:
            return "comparison"
        return "validation"

    def route_after_validation(state: FlowPilotState) -> str:
        if state.get("needs_retry"):
            return "extraction"
        if state.get("needs_escalation"):
            return "reasoning_tier3"
        return "response"

    graph = StateGraph(FlowPilotState)
    graph.add_node("intent_router", intent_router_node)
    graph.add_node("tier0_fast_path", tier0_fast_path_node)
    graph.add_node("tier1_lightweight", tier1_lightweight_node)
    graph.add_node("planner", planner_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("extraction", extraction_node)
    graph.add_node("comparison", comparison_node)
    graph.add_node("validation", validation_node)
    graph.add_node("reasoning_tier3", reasoning_tier3_node)
    graph.add_node("response", response_node)

    graph.add_edge(START, "intent_router")
    graph.add_conditional_edges(
        "intent_router",
        route_after_intent,
        {
            "tier0_fast_path": "tier0_fast_path",
            "tier1_lightweight": "tier1_lightweight",
            "planner": "planner",
        },
    )
    graph.add_conditional_edges(
        "tier0_fast_path",
        route_after_tier0,
        {"validation": "validation", "tier1_lightweight": "tier1_lightweight"},
    )
    graph.add_edge("tier1_lightweight", "validation")
    graph.add_edge("planner", "retrieval")
    graph.add_edge("retrieval", "extraction")
    graph.add_conditional_edges(
        "extraction",
        route_after_extraction,
        {"comparison": "comparison", "validation": "validation"},
    )
    graph.add_edge("comparison", "validation")
    graph.add_conditional_edges(
        "validation",
        route_after_validation,
        {
            "extraction": "extraction",
            "reasoning_tier3": "reasoning_tier3",
            "response": "response",
        },
    )
    graph.add_edge("reasoning_tier3", "response")
    graph.add_edge("response", END)

    return graph.compile(checkpointer=InMemorySaver())


def get_graph_mermaid_diagram() -> str:
    """Export Mermaid visualization of the compiled FlowPilot LangGraph topology."""
    dummy_deps = GraphRuntimeDeps(
        gateway=ModelGateway(),
        budget=WorkflowBudgetTracker(workflow_id="preview", user_id="preview"),
    )
    compiled = build_flowpilot_graph(dummy_deps)
    return compiled.get_graph().draw_mermaid()
