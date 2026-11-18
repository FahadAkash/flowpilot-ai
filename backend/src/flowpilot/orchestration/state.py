"""Typed LangGraph FlowPilotState following mastering-langgraph-agent-skill.

Principles applied:
- Keep state raw (structured facts, never pre-formatted prompts)
- Use `Annotated[list[...], operator.add]` reducers for append-only audit trails
- `from __future__ import annotations` for clean type resolution
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class FlowPilotState(TypedDict, total=False):
    workflow_id: str
    user_id: str
    query: str
    documents: list[dict[str, Any]]
    force_tier: int | None
    confidence_threshold: float

    # Routing & planning
    intent: str
    selected_tier: int
    current_tier: int
    routing_rationale: str
    plan_steps: list[str]
    tier0_handled: bool

    # Working data across specialist agents
    retrieved_chunks: list[dict[str, Any]]
    extracted_records: list[dict[str, Any]]
    discrepancies: list[dict[str, Any]]
    validation_report: dict[str, Any]
    reasoning_output: dict[str, Any]
    tier0_output: dict[str, Any]
    tier1_output: dict[str, Any]

    # Confidence & control flow
    raw_confidence: float
    calibrated_confidence: float
    needs_retry: bool
    needs_escalation: bool
    escalation_reason: str | None
    retry_count: int
    escalation_count: int
    cache_hit: bool

    # Final output
    final_response: dict[str, Any]

    # Append-only execution & telemetry reducers (never overwritten)
    execution_trace: Annotated[list[dict[str, Any]], operator.add]
    model_logs: Annotated[list[dict[str, Any]], operator.add]
    tool_logs: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[dict[str, Any]], operator.add]
