"""Confidence calibration, Expected Calibration Error (ECE), and threshold sweeps.

Follows python-skills/threshold-calibration:
- Measures empirical confidence reliability against ground truth instead of blindly
  trusting self-reported model confidence.
- Supports bidirectional threshold sweeps ("high" and "low").
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(slots=True)
class CalibrationSample:
    raw_confidence: float
    calibrated_confidence: float
    is_correct: bool
    tier: int = 1


@dataclass(slots=True)
class ReliabilityBin:
    bin_index: int
    lower: float
    upper: float
    count: int
    avg_confidence: float
    empirical_accuracy: float
    calibration_gap: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "bin_index": self.bin_index,
            "range": f"{self.lower:.1f}-{self.upper:.1f}",
            "lower": self.lower,
            "upper": self.upper,
            "count": self.count,
            "avg_confidence": round(self.avg_confidence, 4),
            "empirical_accuracy": round(self.empirical_accuracy, 4),
            "calibration_gap": round(self.calibration_gap, 4),
        }


def calibrate_confidence(
    raw_confidence: float,
    *,
    slope: float = 0.92,
    intercept: float = 0.04,
) -> float:
    """Apply linear reliability calibration clamped to [0.0, 1.0]."""
    calibrated = slope * raw_confidence + intercept
    return round(max(0.0, min(1.0, calibrated)), 4)


def compute_reliability_bins(
    samples: list[CalibrationSample],
    *,
    num_bins: int = 5,
    use_calibrated: bool = True,
) -> tuple[float, list[ReliabilityBin]]:
    """Compute Expected Calibration Error (ECE) and per-bin reliability statistics."""
    if not samples:
        return 0.0, []

    bins: list[ReliabilityBin] = []
    total = len(samples)
    ece = 0.0
    width = 1.0 / num_bins

    for idx in range(num_bins):
        lo = round(idx * width, 4)
        hi = round((idx + 1) * width, 4)
        if idx == num_bins - 1:
            members = [
                s
                for s in samples
                if lo <= (s.calibrated_confidence if use_calibrated else s.raw_confidence) <= hi
            ]
        else:
            members = [
                s
                for s in samples
                if lo <= (s.calibrated_confidence if use_calibrated else s.raw_confidence) < hi
            ]
        if not members:
            bins.append(
                ReliabilityBin(
                    bin_index=idx,
                    lower=lo,
                    upper=hi,
                    count=0,
                    avg_confidence=round((lo + hi) / 2, 4),
                    empirical_accuracy=0.0,
                    calibration_gap=0.0,
                )
            )
            continue

        avg_conf = sum(
            s.calibrated_confidence if use_calibrated else s.raw_confidence for s in members
        ) / len(members)
        emp_acc = sum(1.0 for s in members if s.is_correct) / len(members)
        gap = abs(avg_conf - emp_acc)
        ece += (len(members) / total) * gap
        bins.append(
            ReliabilityBin(
                bin_index=idx,
                lower=lo,
                upper=hi,
                count=len(members),
                avg_confidence=avg_conf,
                empirical_accuracy=emp_acc,
                calibration_gap=gap,
            )
        )

    return round(ece, 4), bins


def fit_linear_calibration(samples: list[CalibrationSample]) -> tuple[float, float]:
    """Fit least-squares slope & intercept mapping raw_confidence -> empirical accuracy."""
    if len(samples) < 3:
        return 1.0, 0.0
    xs = [s.raw_confidence for s in samples]
    ys = [1.0 if s.is_correct else 0.0 for s in samples]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom < 1e-6:
        return 1.0, round(mean_y - mean_x, 4)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=False)) / denom
    slope = max(0.25, min(1.25, slope))
    intercept = mean_y - slope * mean_x
    return round(slope, 4), round(intercept, 4)


def threshold_sweep(
    scores: list[float],
    labels: list[bool],
    thresholds: list[float],
    *,
    direction: Literal["high", "low"] = "high",
) -> list[dict[str, float]]:
    """Sweep decision thresholds in either comparison direction and report TPR/FPR/F1."""
    cmp_op = operator.ge if direction == "high" else operator.le
    results: list[dict[str, float]] = []
    for t in thresholds:
        tp = fp = tn = fn = 0
        for s, y in zip(scores, labels, strict=False):
            pred = cmp_op(s, t)
            if pred and y:
                tp += 1
            elif pred and not y:
                fp += 1
            elif not pred and not y:
                tn += 1
            else:
                fn += 1
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        fpr = fp / (fp + tn) if (fp + tn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        results.append(
            {
                "threshold": t,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "fpr": round(fpr, 4),
                "f1": round(f1, 4),
            }
        )
    return results
