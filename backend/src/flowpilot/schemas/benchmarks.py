"""Pydantic v2 schemas for benchmarks, evaluation runs, and analytics."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BenchmarkRunRequest(BaseModel):
    name: str = "Baseline A vs FlowPilot Orchestrator"
    dataset_name: str = "unidoc-bench-curated"
    include_stress_cases: bool = True


class EvaluationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    dataset_name: str
    mode: str
    sample_count: int
    avg_tokens: float
    avg_cost_usd: float
    p50_latency_ms: float
    p95_latency_ms: float
    throughput_rps: float
    field_precision: float
    field_recall: float
    field_f1: float
    classification_f1: float
    escalation_rate: float
    avg_tool_calls: float
    failure_rate: float
    ece_calibration_error: float
    tier_distribution_json: dict[str, Any]
    details_json: dict[str, Any]
    created_at: datetime


class BenchmarkComparisonOut(BaseModel):
    baseline_monolithic: EvaluationRunOut
    flowpilot_orchestrator: EvaluationRunOut
    token_reduction_pct: float
    cost_reduction_pct: float
    p95_latency_reduction_pct: float
    throughput_multiplier: float
    f1_delta: float
    calibration_bins: list[dict[str, Any]] = Field(default_factory=list)
    report_markdown: str = ""
