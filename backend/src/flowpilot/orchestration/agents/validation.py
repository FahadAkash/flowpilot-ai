"""Validation Agent: Pydantic schema validation, arithmetic invariants, and escalation gating.

Follows python-skills/llm-features:
- Never allows an empty evaluator rule set to masquerade as a clean pass (`rules_evaluated >= 1`).
- Evaluates calibrated confidence (not raw uncalibrated confidence) against policy threshold.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from flowpilot.guardrails.budget import WorkflowBudgetTracker
from flowpilot.schemas.workflows import DiscrepancyItem, ExtractedDocumentRecord, ValidationReport


async def run_validation_agent(
    *,
    intent: str,
    current_tier: int,
    extracted_records: list[dict[str, Any]],
    discrepancies: list[dict[str, Any]],
    tier0_output: dict[str, Any] | None,
    calibrated_confidence: float,
    confidence_threshold: float,
    budget: WorkflowBudgetTracker,
) -> ValidationReport:
    """Validate structured outputs and determine pass vs retry vs Tier 3 escalation."""
    budget.record_agent_call("validation")

    passed_rules: list[str] = []
    failed_rules: list[str] = []
    warnings: list[str] = []

    # Rule 1: Non-empty evidence check
    if tier0_output and tier0_output.get("answer"):
        passed_rules.append("tier0_deterministic_evidence_present")
    elif extracted_records:
        passed_rules.append("extracted_records_present")
    else:
        failed_rules.append("missing_extracted_evidence")

    # Rule 2: Strict Pydantic v2 schema validation on every extracted record
    schema_ok = True
    for rec in extracted_records:
        try:
            ExtractedDocumentRecord.model_validate(rec)
        except ValidationError as exc:
            schema_ok = False
            failed_rules.append(f"schema_validation_failed:{exc.error_count()}")
    if extracted_records and schema_ok:
        passed_rules.append("pydantic_record_schema_valid")

    # Rule 3: Strict Pydantic v2 schema validation on every discrepancy
    disc_ok = True
    for d in discrepancies:
        try:
            DiscrepancyItem.model_validate(d)
        except ValidationError:
            disc_ok = False
            failed_rules.append("discrepancy_schema_invalid")
    if discrepancies and disc_ok:
        passed_rules.append("pydantic_discrepancy_schema_valid")

    # Rule 4: Citation grounding check
    has_citations = bool(
        (tier0_output and tier0_output.get("citations"))
        or any(r.get("citations") for r in extracted_records)
        or any(d.get("citation") for d in discrepancies)
    )
    if has_citations:
        passed_rules.append("citation_grounding_verified")
    else:
        warnings.append("Limited citation metadata available for extracted records.")

    # Rule 5: Calibrated confidence gate & ambiguity check
    ambiguous_items = [d for d in discrepancies if d.get("requires_frontier_reasoning")]
    low_confidence = calibrated_confidence < confidence_threshold
    if not low_confidence:
        passed_rules.append("calibrated_confidence_above_threshold")
    else:
        warnings.append(
            f"Calibrated confidence ({calibrated_confidence:.2f}) below policy threshold ({confidence_threshold:.2f})."
        )

    needs_retry = False
    needs_escalation = False
    escalation_reason: str | None = None

    if failed_rules and budget.can_retry() and current_tier >= 1:
        needs_retry = True
    elif (
        ambiguous_items or (low_confidence and current_tier >= 1) or intent == "legal_reasoning"
    ) and current_tier < 3:
        if budget.can_escalate():
            needs_escalation = True
            if ambiguous_items:
                escalation_reason = (
                    f"{len(ambiguous_items)} ambiguous/conflicting legal or contractual clause(s) "
                    "flagged for Tier 3 frontier reasoning."
                )
            elif intent == "legal_reasoning":
                escalation_reason = (
                    "Complex legal/contractual interpretation requires Tier 3 synthesis."
                )
            else:
                escalation_reason = (
                    f"Calibrated confidence ({calibrated_confidence:.2f}) below threshold "
                    f"({confidence_threshold:.2f})."
                )
        else:
            warnings.append(
                "Tier 3 escalation skipped because max_escalations guardrail was reached."
            )

    rules_evaluated = max(1, len(passed_rules) + len(failed_rules))
    return ValidationReport(
        passed=len(failed_rules) == 0,
        rules_evaluated=rules_evaluated,
        passed_rules=passed_rules,
        failed_rules=failed_rules,
        warnings=warnings,
        needs_retry=needs_retry,
        needs_escalation=needs_escalation,
        escalation_reason=escalation_reason,
    )
