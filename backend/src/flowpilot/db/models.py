"""SQLAlchemy 2.0 ORM models for all 12 FlowPilot AI core tables.

Key architectural principle:
Workflow execution state (`workflows`, `workflow_steps`) is strictly separated from
model & tool invocation telemetry (`model_invocations`, `tool_invocations`, `workflow_metrics`)
so operators can audit tier selection, cost breakdown, and latency per agent independently.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def new_uuid() -> str:
    """Generate a canonical string UUID."""
    return str(uuid.uuid4())


class PortableVector(TypeDecorator[list[float]]):
    """Stores embeddings as pgvector Vector(dim) on PostgreSQL and JSON on SQLite."""

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int = 384) -> None:
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: list[float] | None, dialect: Any) -> Any:
        if value is None:
            return None
        return [float(v) for v in value]

    def process_result_value(self, value: Any, dialect: Any) -> list[float] | None:
        if value is None:
            return None
        if isinstance(value, list):
            return [float(v) for v in value]
        return [float(v) for v in list(value)]


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 declarative base."""


# 1. users
class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="FlowPilot User")
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="analyst")
    api_key_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    documents: Mapped[list[Document]] = relationship(back_populates="user")
    workflows: Mapped[list[Workflow]] = relationship(back_populates="user")


# 2. documents
class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="documents")
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


# 3. document_chunks
class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    section_title: Mapped[str] = mapped_column(String(255), nullable=False, default="Body")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding: Mapped[list[float] | None] = mapped_column(PortableVector(384), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped[Document] = relationship(back_populates="chunks")


# 4. workflows
class Workflow(Base):
    __tablename__ = "workflows"
    __table_args__ = (
        Index("ix_workflows_user_idempotency", "user_id", "idempotency_key", unique=False),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    document_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    intent: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    selected_tier: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    final_tier: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    routing_rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    final_response_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    raw_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    calibrated_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    escalation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    step_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    agent_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="workflows")
    steps: Mapped[list[WorkflowStep]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="WorkflowStep.step_index",
    )
    model_invocations: Mapped[list[ModelInvocation]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
    )
    tool_invocations: Mapped[list[ToolInvocation]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
    )
    metrics: Mapped[WorkflowMetric | None] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
        uselist=False,
    )


# 5. workflow_steps
class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    node_name: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    routing_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    input_summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output_summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workflow: Mapped[Workflow] = relationship(back_populates="steps")


# 6. agents
class AgentConfig(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(255), nullable=False)
    default_tier: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    default_model_key: Mapped[str] = mapped_column(
        String(128), nullable=False, default="deterministic"
    )
    max_tool_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1.0")
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# 7. model_registry
class ModelRegistry(Base):
    __tablename__ = "model_registry"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    model_key: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    input_cost_per_1k: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    output_cost_per_1k: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_context_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=128_000)
    avg_latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    calibration_slope: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    calibration_intercept: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# 8. model_invocations
class ModelInvocation(Base):
    __tablename__ = "model_invocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    workflow_step_id: Mapped[str | None] = mapped_column(
        ForeignKey("workflow_steps.id", ondelete="SET NULL"),
        nullable=True,
    )
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    raw_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    calibrated_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="success")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    workflow: Mapped[Workflow] = relationship(back_populates="model_invocations")


# 9. tool_invocations
class ToolInvocation(Base):
    __tablename__ = "tool_invocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    workflow_step_id: Mapped[str | None] = mapped_column(
        ForeignKey("workflow_steps.id", ondelete="SET NULL"),
        nullable=True,
    )
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    arguments_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    result_summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="success")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    workflow: Mapped[Workflow] = relationship(back_populates="tool_invocations")


# 10. budget_policies
class BudgetPolicy(Base):
    __tablename__ = "budget_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="global")
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    task_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    max_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    max_agent_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    max_tokens_per_workflow: Mapped[int] = mapped_column(Integer, nullable=False, default=10_000)
    max_cost_per_workflow_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.50)
    daily_cost_limit_usd: Mapped[float] = mapped_column(Float, nullable=False, default=25.0)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    max_tool_calls_per_agent: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    max_escalations: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    confidence_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.80)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


# 11. workflow_metrics
class WorkflowMetric(Base):
    __tablename__ = "workflow_metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    tier_used: Mapped[int] = mapped_column(Integer, nullable=False)
    escalated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_baseline_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    estimated_baseline_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    savings_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tool_calls_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    agent_calls_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    step_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    workflow: Mapped[Workflow] = relationship(back_populates="metrics")


# 12. evaluation_runs
class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_name: Mapped[str] = mapped_column(
        String(128), nullable=False, default="unidoc-bench-curated"
    )
    mode: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_tokens: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    p50_latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    p95_latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    throughput_rps: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    field_precision: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    field_recall: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    field_f1: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    classification_f1: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    escalation_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_tool_calls: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    failure_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ece_calibration_error: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tier_distribution_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
