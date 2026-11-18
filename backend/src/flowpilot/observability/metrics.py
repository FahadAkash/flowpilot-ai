"""Prometheus metrics for FlowPilot AI tier routing, costs, latency, and guardrails."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, generate_latest

WORKFLOWS_TOTAL = Counter(
    "flowpilot_workflows_total",
    "Total workflows executed by tier, status, and intent",
    ["tier", "status", "intent"],
)

WORKFLOW_LATENCY_SECONDS = Histogram(
    "flowpilot_workflow_latency_seconds",
    "Workflow end-to-end execution latency in seconds",
    ["tier"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

TOKENS_TOTAL = Counter(
    "flowpilot_tokens_total",
    "Total LLM tokens consumed",
    ["tier", "model", "direction"],
)

COST_USD_TOTAL = Counter(
    "flowpilot_cost_usd_total",
    "Total USD cost incurred across LLM invocations",
    ["tier", "model"],
)

ESTIMATED_SAVINGS_USD_TOTAL = Counter(
    "flowpilot_estimated_savings_usd_total",
    "Estimated USD cost saved compared to monolithic frontier baseline",
)

ESCALATIONS_TOTAL = Counter(
    "flowpilot_escalations_total",
    "Total tier escalations triggered",
    ["from_tier", "to_tier", "reason"],
)

GUARDRAIL_TRIPS_TOTAL = Counter(
    "flowpilot_guardrail_trips_total",
    "Total guardrail violations intercepted",
    ["guardrail_type"],
)

CACHE_HITS_TOTAL = Counter(
    "flowpilot_cache_hits_total",
    "Total Tier 0 deterministic cache hits",
    ["cache_type"],
)

CIRCUIT_BREAKER_STATE = Gauge(
    "flowpilot_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half_open, 2=open)",
    ["provider_key"],
)

ACTIVE_WORKFLOWS = Gauge(
    "flowpilot_active_workflows",
    "Number of currently executing workflows",
)


def render_prometheus_metrics() -> bytes:
    """Serialize current Prometheus registry metrics."""
    return generate_latest()
