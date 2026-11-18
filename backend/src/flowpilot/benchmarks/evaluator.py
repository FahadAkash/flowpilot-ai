"""Evaluation metrics: field-level Precision/Recall/F1, classification F1, latency p50/p95, ECE."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from flowpilot.benchmarks.dataset import BenchmarkCase
from flowpilot.llm.calibration import CalibrationSample, compute_reliability_bins


@dataclass(slots=True)
class CaseOutcome:
    case_id: str
    category: str
    tier_used: int
    escalated: bool
    tokens: int
    cost_usd: float
    latency_ms: float
    tool_calls: int
    succeeded: bool
    raw_confidence: float
    calibrated_confidence: float
    tp: int = 0
    fp: int = 0
    fn: int = 0
    classification_correct: bool | None = None
    is_overall_correct: bool = True


def score_case_against_ground_truth(
    case: BenchmarkCase,
    final_response: dict[str, Any],
) -> tuple[int, int, int, bool | None, bool]:
    """Compute field/discrepancy TP, FP, FN and classification accuracy for one case."""
    tp = fp = fn = 0
    cls_correct: bool | None = None

    # 1. Classification evaluation
    if case.ground_truth_doc_type is not None:
        recs = final_response.get("extracted_records") or []
        pred_type = None
        if recs:
            pred_type = recs[0].get("doc_type")
        if pred_type is None:
            pred_type = (final_response.get("extracted_fields") or {}).get("doc_type")
        cls_correct = str(pred_type or "").lower() == case.ground_truth_doc_type.lower()
        if cls_correct:
            tp += 1
        else:
            fn += 1
            fp += 1

    # 2. Field-level extraction evaluation
    if case.ground_truth_fields:
        pred_fields: dict[str, Any] = dict(final_response.get("extracted_fields") or {})
        recs = final_response.get("extracted_records") or []
        if recs and isinstance(recs[0], dict):
            for k, v in recs[0].items():
                if k not in pred_fields and v is not None:
                    pred_fields[k] = v

        for k, expected_val in case.ground_truth_fields.items():
            actual_val = pred_fields.get(k)
            if _values_match(expected_val, actual_val):
                tp += 1
            else:
                fn += 1
                if actual_val is not None:
                    fp += 1

    # 3. Discrepancy set evaluation (for multi-doc comparisons & contract conflicts)
    if case.category.startswith("tier2_") or case.category.startswith("tier3_"):
        expected_codes = set(case.ground_truth_discrepancy_codes)
        pred_codes = {
            str(d.get("code")) for d in (final_response.get("discrepancies") or []) if d.get("code")
        }
        if not expected_codes and not pred_codes:
            # True negative (clean compliant pair verified with 0 false positives)
            tp += 1
        else:
            tp += len(expected_codes & pred_codes)
            fp += len(pred_codes - expected_codes)
            fn += len(expected_codes - pred_codes)

    overall_correct = (fn == 0 and fp == 0) and (cls_correct is not False)
    return tp, fp, fn, cls_correct, overall_correct


def _values_match(expected: Any, actual: Any) -> bool:
    if actual is None:
        return False
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(expected) - float(actual)) <= 0.05
    return str(expected).strip().lower() == str(actual).strip().lower()


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, math.ceil((pct / 100.0) * len(ordered)) - 1))
    return round(ordered[idx], 2)


@dataclass
class AggregateBenchmarkMetrics:
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
    tier_distribution: dict[str, int] = field(default_factory=dict)
    calibration_bins: list[dict[str, Any]] = field(default_factory=list)
    outcomes: list[dict[str, Any]] = field(default_factory=list)


def aggregate_outcomes(mode: str, outcomes: list[CaseOutcome]) -> AggregateBenchmarkMetrics:
    """Aggregate per-case outcomes into all 9 benchmark KPIs + ECE calibration."""
    n = max(1, len(outcomes))
    avg_tokens = round(sum(o.tokens for o in outcomes) / n, 2)
    avg_cost = round(sum(o.cost_usd for o in outcomes) / n, 6)
    latencies = [o.latency_ms for o in outcomes]
    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)

    # Throughput modeled from effective simulated request latency (4 concurrent workers)
    total_latency_sec = max(0.001, sum(latencies) / 1000.0)
    throughput_rps = round((len(outcomes) / total_latency_sec) * 4.0, 2)

    tot_tp = sum(o.tp for o in outcomes)
    tot_fp = sum(o.fp for o in outcomes)
    tot_fn = sum(o.fn for o in outcomes)
    precision = tot_tp / (tot_tp + tot_fp) if (tot_tp + tot_fp) else 0.0
    recall = tot_tp / (tot_tp + tot_fn) if (tot_tp + tot_fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    cls_cases = [o for o in outcomes if o.classification_correct is not None]
    cls_f1 = (
        sum(1.0 for o in cls_cases if o.classification_correct) / len(cls_cases)
        if cls_cases
        else f1
    )

    esc_rate = round(sum(1 for o in outcomes if o.escalated) / n, 4)
    avg_tools = round(sum(o.tool_calls for o in outcomes) / n, 2)
    fail_rate = round(sum(1 for o in outcomes if not o.succeeded) / n, 4)

    cal_samples = [
        CalibrationSample(
            raw_confidence=o.raw_confidence,
            calibrated_confidence=o.calibrated_confidence,
            is_correct=o.is_overall_correct,
            tier=o.tier_used,
        )
        for o in outcomes
    ]
    ece, bins = compute_reliability_bins(cal_samples, num_bins=5, use_calibrated=True)

    tier_dist = {"tier_0": 0, "tier_1": 0, "tier_2": 0, "tier_3": 0}
    for o in outcomes:
        key = f"tier_{max(0, min(3, o.tier_used))}"
        tier_dist[key] += 1

    return AggregateBenchmarkMetrics(
        mode=mode,
        sample_count=len(outcomes),
        avg_tokens=avg_tokens,
        avg_cost_usd=avg_cost,
        p50_latency_ms=p50,
        p95_latency_ms=p95,
        throughput_rps=throughput_rps,
        field_precision=round(precision, 4),
        field_recall=round(recall, 4),
        field_f1=round(f1, 4),
        classification_f1=round(cls_f1, 4),
        escalation_rate=esc_rate,
        avg_tool_calls=avg_tools,
        failure_rate=fail_rate,
        ece_calibration_error=ece,
        tier_distribution=tier_dist,
        calibration_bins=[b.to_dict() for b in bins],
        outcomes=[
            {
                "case_id": o.case_id,
                "category": o.category,
                "tier_used": o.tier_used,
                "escalated": o.escalated,
                "tokens": o.tokens,
                "cost_usd": o.cost_usd,
                "latency_ms": o.latency_ms,
                "tool_calls": o.tool_calls,
                "succeeded": o.succeeded,
                "calibrated_confidence": o.calibrated_confidence,
                "is_correct": o.is_overall_correct,
            }
            for o in outcomes
        ],
    )
