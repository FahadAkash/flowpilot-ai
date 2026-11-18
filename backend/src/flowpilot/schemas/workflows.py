"""Pydantic v2 schemas for workflows, agents, extraction, discrepancies, and telemetry."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LineItem(BaseModel):
    description: str
    quantity: float = 1.0
    unit_price: float = 0.0
    line_total: float = 0.0


class ExtractedDocumentRecord(BaseModel):
    """Typed structured extraction output validated by the Validation Agent."""

    document_id: str
    filename: str
    doc_type: str
    document_number: str | None = None
    reference_po_number: str | None = None
    vendor: str | None = None
    buyer: str | None = None
    issue_date: str | None = None
    due_date: str | None = None
    payment_terms: str | None = None
    currency: str = "USD"
    subtotal: float | None = None
    tax_amount: float | None = None
    total_amount: float | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    policy_rules: dict[str, Any] = Field(default_factory=dict)
    contract_clauses: dict[str, str] = Field(default_factory=dict)
    key_dates: dict[str, str] = Field(default_factory=dict)
    citations: list[str] = Field(default_factory=list)


class DiscrepancyItem(BaseModel):
    """Hedged, evidence-backed finding produced by Comparison / Reasoning Agents."""

    code: str
    category: Literal[
        "amount_mismatch",
        "quantity_mismatch",
        "unit_price_mismatch",
        "terms_mismatch",
        "policy_concern",
        "contract_conflict",
        "missing_approval",
        "calculation_error",
        "date_mismatch",
    ]
    severity: Literal["low", "medium", "high", "critical"]
    field: str
    expected: str
    actual: str
    potential_concern: str = Field(
        description="Potential discrepancy or policy concern grounded in cited document text."
    )
    citation: str
    requires_frontier_reasoning: bool = False


class ValidationReport(BaseModel):
    """Output of the Validation Agent; ensures non-empty rule evaluation."""

    passed: bool
    rules_evaluated: int = Field(ge=1)
    passed_rules: list[str] = Field(default_factory=list)
    failed_rules: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    needs_retry: bool = False
    needs_escalation: bool = False
    escalation_reason: str | None = None


class WorkflowExecuteRequest(BaseModel):
    query: str = Field(min_length=2, max_length=4000)
    document_ids: list[str] = Field(default_factory=list)
    force_tier: int | None = Field(default=None, ge=0, le=3)
    async_mode: bool = False
    confidence_threshold_override: float | None = Field(default=None, ge=0.0, le=1.0)


class WorkflowStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    step_index: int
    node_name: str
    agent_name: str
    tier: int
    status: str
    routing_reason: str
    input_summary_json: dict[str, Any]
    output_summary_json: dict[str, Any]
    confidence: float | None
    latency_ms: float
    tokens_used: int
    cost_usd: float
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None


class ModelInvocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workflow_step_id: str | None
    agent_name: str
    model_key: str
    provider: str
    tier: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: float
    raw_confidence: float | None
    calibrated_confidence: float | None
    cache_hit: bool
    status: str
    error_code: str | None
    created_at: datetime


class ToolInvocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workflow_step_id: str | None
    agent_name: str
    tool_name: str
    arguments_json: dict[str, Any]
    result_summary_json: dict[str, Any]
    latency_ms: float
    status: str
    error_message: str | None
    created_at: datetime


class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    idempotency_key: str | None
    query: str
    document_ids: list[str]
    intent: str
    selected_tier: int
    final_tier: int
    routing_rationale: str
    status: str
    final_response_json: dict[str, Any]
    raw_confidence: float
    calibrated_confidence: float
    escalation_count: int
    retry_count: int
    step_count: int
    agent_call_count: int
    tool_call_count: int
    total_tokens: int
    total_cost_usd: float
    latency_ms: float
    cache_hit: bool
    error_json: dict[str, Any] | None
    created_at: datetime
    completed_at: datetime | None


class WorkflowTraceOut(WorkflowOut):
    steps: list[WorkflowStepOut] = Field(default_factory=list)
    model_invocations: list[ModelInvocationOut] = Field(default_factory=list)
    tool_invocations: list[ToolInvocationOut] = Field(default_factory=list)
    estimated_baseline_cost_usd: float = 0.0
    estimated_baseline_tokens: int = 0
    savings_usd: float = 0.0
    skipped_agents: list[str] = Field(default_factory=list)
