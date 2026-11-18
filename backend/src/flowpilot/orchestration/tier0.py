"""Tier 0 Deterministic Fast Path + reusable regex/rule extraction & arithmetic verification.

Zero LLM tokens are consumed for deterministic lookups, date extraction, arithmetic totals,
and rule-based validation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from flowpilot.schemas.workflows import DiscrepancyItem, ExtractedDocumentRecord, LineItem

INVOICE_NUM_RE = re.compile(
    r"(?:invoice\s*(?:number|no\.?|#)\s*[:#-]?\s*)([A-Z]{2,6}-[A-Z0-9-]{3,16}|\d{4,12})",
    re.IGNORECASE,
)
PO_NUM_RE = re.compile(
    r"(?:(?:purchase\s+order|p\.?o\.?)\s*(?:number|no\.?|#|ref(?:erence)?)?\s*[:#-]?\s*)(PO-[A-Z0-9-]{3,16})",
    re.IGNORECASE,
)
CONTRACT_NUM_RE = re.compile(
    r"(?:(?:contract|agreement)\s*(?:id|number|no\.?|#)\s*[:#-]?\s*)([A-Z]{2,6}-[A-Z0-9-]{3,16})",
    re.IGNORECASE,
)
VENDOR_RE = re.compile(r"(?:vendor|supplier|from|seller)\s*[:]\s*([^\n\r]{2,80})", re.IGNORECASE)
BUYER_RE = re.compile(
    r"(?:buyer|bill\s+to|client|customer|ship\s+to)\s*[:]\s*([^\n\r]{2,80})", re.IGNORECASE
)
ISSUE_DATE_RE = re.compile(
    r"(?:invoice\s+date|issue\s+date|order\s+date|effective\s+date|date)\s*[:]\s*"
    r"(\d{4}-\d{2}-\d{2}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE,
)
DUE_DATE_RE = re.compile(
    r"(?:due\s+date|payment\s+due|expiration\s+date)\s*[:]\s*"
    r"(\d{4}-\d{2}-\d{2}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE,
)
PAYMENT_TERMS_RE = re.compile(
    r"(?:payment\s+terms|terms)\s*[:]\s*(Net\s+\d{1,3}|Due\s+on\s+Receipt|[^\n\r]{3,40})",
    re.IGNORECASE,
)
SUBTOTAL_RE = re.compile(
    r"(?:sub\s*-?total)\s*[:]\s*\$?\s*([0-9][0-9,]*(?:\.\d{1,2})?)", re.IGNORECASE
)
TAX_RE = re.compile(
    r"(?:sales\s+tax|vat|tax(?:\s*\([^)]+\))?)\s*[:]\s*\$?\s*([0-9][0-9,]*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
TOTAL_RE = re.compile(
    r"(?:grand\s+total|total\s+amount(?:\s+due)?|amount\s+due|invoice\s+total|total\s+authorized|total)\s*[:]\s*\$?\s*([0-9][0-9,]*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
LINE_ITEM_RE = re.compile(
    r"^\s*(?:[-*•]\s*)?(?P<desc>[A-Za-z0-9][^|\n\r]{2,60}?)\s*(?:\||—|-)\s*"
    r"(?:Qty\s*[:=]?\s*)?(?P<qty>\d+(?:\.\d+)?)\s*(?:x|×|@)\s*\$?(?P<unit>[0-9][0-9,]*(?:\.\d{1,2})?)\s*"
    r"(?:=|\|)\s*\$?(?P<total>[0-9][0-9,]*(?:\.\d{1,2})?)",
    re.IGNORECASE | re.MULTILINE,
)

# Policy rule extractors
MAX_AUTO_APPROVAL_RE = re.compile(
    r"(?:auto-?approv\w*|without\s+(?:vp|executive|cfo)\s+approval|single\s+invoice\s+(?:limit|cap))[^$\n\r]{0,60}\$\s*([0-9][0-9,]*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
VARIANCE_TOLERANCE_RE = re.compile(
    r"(?:price|amount|budget)?\s*(?:variance|tolerance)[^%\n\r]{0,50}(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
MAX_PAYMENT_DAYS_RE = re.compile(
    r"(?:standard|maximum|minimum|required)\s+payment\s+terms[^0-9\n\r]{0,35}Net\s+(\d{1,3})",
    re.IGNORECASE,
)
APPROVED_VENDORS_RE = re.compile(r"(?:approved\s+vendors?)\s*[:]\s*([^\n\r]+)", re.IGNORECASE)


def _to_float(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        return round(float(raw.replace(",", "").strip()), 2)
    except ValueError:
        return None


def _normalize_date(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = raw.strip().rstrip(".")
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return cleaned


def _extract_clause(text: str, heading_keywords: tuple[str, ...]) -> str | None:
    for line in text.splitlines():
        low = line.lower()
        if any(k in low for k in heading_keywords):
            cleaned = line.strip()
            if len(cleaned) > 12:
                return cleaned
    return None


def extract_structured_record(doc: dict[str, Any]) -> ExtractedDocumentRecord:
    """Deterministically extract structured fields, policy rules, and clauses from a document."""
    text = str(doc.get("raw_text") or "")
    filename = str(doc.get("filename") or "document.pdf")
    doc_type = str(doc.get("doc_type") or "general_document")
    doc_id = str(doc.get("id") or "")

    inv_m = INVOICE_NUM_RE.search(text)
    po_m = PO_NUM_RE.search(text)
    ctr_m = CONTRACT_NUM_RE.search(text)
    vendor_m = VENDOR_RE.search(text)
    buyer_m = BUYER_RE.search(text)
    issue_m = ISSUE_DATE_RE.search(text)
    due_m = DUE_DATE_RE.search(text)
    terms_m = PAYMENT_TERMS_RE.search(text)
    subtotal_m = SUBTOTAL_RE.search(text)
    tax_m = TAX_RE.search(text)
    total_matches = TOTAL_RE.findall(text)

    doc_number = None
    ref_po = None
    if doc_type == "invoice":
        doc_number = inv_m.group(1).strip() if inv_m else None
        ref_po = po_m.group(1).strip() if po_m else None
    elif doc_type == "purchase_order":
        doc_number = po_m.group(1).strip() if po_m else None
    elif doc_type == "contract":
        doc_number = ctr_m.group(1).strip() if ctr_m else None
    else:
        doc_number = (
            inv_m.group(1).strip()
            if inv_m
            else (po_m.group(1).strip() if po_m else (ctr_m.group(1).strip() if ctr_m else None))
        )

    line_items: list[LineItem] = []
    for m in LINE_ITEM_RE.finditer(text):
        qty = _to_float(m.group("qty")) or 1.0
        unit = _to_float(m.group("unit")) or 0.0
        total = _to_float(m.group("total")) or round(qty * unit, 2)
        line_items.append(
            LineItem(
                description=m.group("desc").strip(),
                quantity=qty,
                unit_price=unit,
                line_total=total,
            )
        )

    policy_rules: dict[str, Any] = {}
    if doc_type == "policy" or "policy" in text.lower():
        cap_m = MAX_AUTO_APPROVAL_RE.search(text)
        if cap_m:
            policy_rules["max_auto_approval_usd"] = _to_float(cap_m.group(1))
        var_m = VARIANCE_TOLERANCE_RE.search(text)
        if var_m:
            policy_rules["variance_tolerance_pct"] = _to_float(var_m.group(1))
        days_m = MAX_PAYMENT_DAYS_RE.search(text)
        if days_m:
            policy_rules["standard_payment_terms_days"] = int(days_m.group(1))
        vend_m = APPROVED_VENDORS_RE.search(text)
        if vend_m:
            policy_rules["approved_vendors"] = [
                v.strip() for v in vend_m.group(1).split(",") if v.strip()
            ]
        if "vp approval" in text.lower() or "cfo approval" in text.lower():
            policy_rules["requires_executive_approval_above_cap"] = True

    contract_clauses: dict[str, str] = {}
    if doc_type == "contract" or "agreement" in text.lower():
        for key, kws in [
            ("payment_terms", ("payment term", "net ", "days of invoice")),
            ("liability_cap", ("liability", "cap", "aggregate liability")),
            ("indemnification", ("indemnif", "hold harmless")),
            ("termination", ("terminat", "notice period")),
            ("governing_law", ("governing law", "jurisdiction", "venue")),
            ("late_fee", ("late fee", "interest", "overdue")),
        ]:
            clause = _extract_clause(text, kws)
            if clause:
                contract_clauses[key] = clause

    key_dates: dict[str, str] = {}
    norm_issue = _normalize_date(issue_m.group(1)) if issue_m else None
    norm_due = _normalize_date(due_m.group(1)) if due_m else None
    if norm_issue:
        key_dates["issue_date"] = norm_issue
    if norm_due:
        key_dates["due_date"] = norm_due

    total_amount = _to_float(total_matches[-1]) if total_matches else None
    citations = [f"{filename} (Page 1)"]

    return ExtractedDocumentRecord(
        document_id=doc_id,
        filename=filename,
        doc_type=doc_type,
        document_number=doc_number,
        reference_po_number=ref_po,
        vendor=vendor_m.group(1).strip() if vendor_m else None,
        buyer=buyer_m.group(1).strip() if buyer_m else None,
        issue_date=norm_issue,
        due_date=norm_due,
        payment_terms=terms_m.group(1).strip() if terms_m else None,
        subtotal=_to_float(subtotal_m.group(1)) if subtotal_m else None,
        tax_amount=_to_float(tax_m.group(1)) if tax_m else None,
        total_amount=total_amount,
        line_items=line_items,
        policy_rules=policy_rules,
        contract_clauses=contract_clauses,
        key_dates=key_dates,
        citations=citations,
    )


def compare_extracted_records(records: list[ExtractedDocumentRecord]) -> list[DiscrepancyItem]:
    """Deterministic cross-document comparison for Invoice vs PO vs Policy and Contract vs Contract."""
    discrepancies: list[DiscrepancyItem] = []

    invoices = [r for r in records if r.doc_type == "invoice"]
    pos = [r for r in records if r.doc_type == "purchase_order"]
    policies = [r for r in records if r.doc_type == "policy"]
    contracts = [r for r in records if r.doc_type == "contract"]

    # 1. Invoice internal arithmetic check
    for inv in invoices:
        if inv.subtotal is not None and inv.tax_amount is not None and inv.total_amount is not None:
            expected_total = round(inv.subtotal + inv.tax_amount, 2)
            if abs(expected_total - inv.total_amount) > 0.02:
                discrepancies.append(
                    DiscrepancyItem(
                        code="INV_ARITHMETIC_MISMATCH",
                        category="calculation_error",
                        severity="high",
                        field="total_amount",
                        expected=f"${expected_total:,.2f} (subtotal + tax)",
                        actual=f"${inv.total_amount:,.2f}",
                        potential_concern=(
                            f"Invoice {inv.document_number or inv.filename} total does not equal "
                            f"subtotal (${inv.subtotal:,.2f}) + tax (${inv.tax_amount:,.2f})."
                        ),
                        citation=f"{inv.filename} (Page 1)",
                    )
                )
        if inv.line_items and inv.subtotal is not None:
            line_sum = round(sum(li.line_total for li in inv.line_items), 2)
            if abs(line_sum - inv.subtotal) > 0.05:
                discrepancies.append(
                    DiscrepancyItem(
                        code="INV_LINE_SUM_MISMATCH",
                        category="calculation_error",
                        severity="medium",
                        field="subtotal",
                        expected=f"${line_sum:,.2f} (sum of line items)",
                        actual=f"${inv.subtotal:,.2f}",
                        potential_concern="Sum of invoice line items differs from stated subtotal.",
                        citation=f"{inv.filename} (Page 1)",
                    )
                )

    # 2. Invoice vs Purchase Order 2-way comparison
    for inv in invoices:
        matched_po = pos[0] if pos else None
        if inv.reference_po_number:
            for p in pos:
                if (
                    p.document_number
                    and p.document_number.upper() == inv.reference_po_number.upper()
                ):
                    matched_po = p
                    break
        if matched_po is None:
            continue

        if inv.total_amount is not None and matched_po.total_amount is not None:
            diff = round(inv.total_amount - matched_po.total_amount, 2)
            if abs(diff) > 0.02:
                pct = abs(diff) / max(matched_po.total_amount, 0.01) * 100.0
                severity: Literal["low", "medium", "high", "critical"] = (
                    "critical" if pct >= 10.0 else ("high" if pct >= 5.0 else "medium")
                )
                discrepancies.append(
                    DiscrepancyItem(
                        code="INV_PO_TOTAL_MISMATCH",
                        category="amount_mismatch",
                        severity=severity,
                        field="total_amount",
                        expected=f"${matched_po.total_amount:,.2f} ({matched_po.filename})",
                        actual=f"${inv.total_amount:,.2f} ({inv.filename})",
                        potential_concern=(
                            f"Invoice total exceeds/differs from PO total by ${diff:+,.2f} ({pct:.1f}%)."
                        ),
                        citation=f"{inv.filename} (Page 1) vs {matched_po.filename} (Page 1)",
                    )
                )

        if (
            inv.payment_terms
            and matched_po.payment_terms
            and inv.payment_terms.lower() != matched_po.payment_terms.lower()
        ):
            discrepancies.append(
                DiscrepancyItem(
                    code="INV_PO_TERMS_MISMATCH",
                    category="terms_mismatch",
                    severity="medium",
                    field="payment_terms",
                    expected=f"{matched_po.payment_terms} ({matched_po.filename})",
                    actual=f"{inv.payment_terms} ({inv.filename})",
                    potential_concern=(
                        f"Invoice payment terms ({inv.payment_terms}) do not match authorized "
                        f"PO terms ({matched_po.payment_terms})."
                    ),
                    citation=f"{inv.filename} (Page 1) vs {matched_po.filename} (Page 1)",
                )
            )

        # Line-item level comparison
        po_items = {li.description.lower(): li for li in matched_po.line_items}
        for inv_li in inv.line_items:
            po_li = po_items.get(inv_li.description.lower())
            if po_li is None:
                # Fuzzy prefix match
                for k, cand in po_items.items():
                    if inv_li.description.lower()[:12] in k or k[:12] in inv_li.description.lower():
                        po_li = cand
                        break
            if po_li is None:
                continue
            if abs(inv_li.quantity - po_li.quantity) > 0.01:
                discrepancies.append(
                    DiscrepancyItem(
                        code="LINE_QTY_MISMATCH",
                        category="quantity_mismatch",
                        severity="high",
                        field=f"line_item:{inv_li.description}:quantity",
                        expected=f"{po_li.quantity:g}",
                        actual=f"{inv_li.quantity:g}",
                        potential_concern=(
                            f"Quantity billed for '{inv_li.description}' ({inv_li.quantity:g}) "
                            f"differs from PO quantity ({po_li.quantity:g})."
                        ),
                        citation=f"{inv.filename} (Page 1) vs {matched_po.filename} (Page 1)",
                    )
                )
            if abs(inv_li.unit_price - po_li.unit_price) > 0.01:
                discrepancies.append(
                    DiscrepancyItem(
                        code="LINE_PRICE_MISMATCH",
                        category="unit_price_mismatch",
                        severity="high",
                        field=f"line_item:{inv_li.description}:unit_price",
                        expected=f"${po_li.unit_price:,.2f}",
                        actual=f"${inv_li.unit_price:,.2f}",
                        potential_concern=(
                            f"Unit price for '{inv_li.description}' (${inv_li.unit_price:,.2f}) "
                            f"differs from PO unit price (${po_li.unit_price:,.2f})."
                        ),
                        citation=f"{inv.filename} (Page 1) vs {matched_po.filename} (Page 1)",
                    )
                )

    # 3. Invoice / PO vs Company Policy 3-way check
    for pol in policies:
        rules = pol.policy_rules
        for inv in invoices:
            cap = rules.get("max_auto_approval_usd")
            if cap is not None and inv.total_amount is not None and inv.total_amount > cap:
                discrepancies.append(
                    DiscrepancyItem(
                        code="POLICY_APPROVAL_THRESHOLD",
                        category="missing_approval",
                        severity="high",
                        field="total_amount",
                        expected=f"<= ${cap:,.2f} auto-approval limit ({pol.filename})",
                        actual=f"${inv.total_amount:,.2f} ({inv.filename})",
                        potential_concern=(
                            f"Invoice amount (${inv.total_amount:,.2f}) exceeds the policy auto-approval "
                            f"cap (${cap:,.2f}) and may require executive/VP sign-off."
                        ),
                        citation=f"{pol.filename} (Page 1) & {inv.filename} (Page 1)",
                    )
                )

            std_days = rules.get("standard_payment_terms_days")
            if std_days is not None and inv.payment_terms:
                m_days = re.search(r"(\d+)", inv.payment_terms)
                if m_days and int(m_days.group(1)) < int(std_days):
                    discrepancies.append(
                        DiscrepancyItem(
                            code="POLICY_PAYMENT_TERMS_CONCERN",
                            category="policy_concern",
                            severity="medium",
                            field="payment_terms",
                            expected=f"Minimum Net {std_days} ({pol.filename})",
                            actual=f"{inv.payment_terms} ({inv.filename})",
                            potential_concern=(
                                f"Invoice payment terms ({inv.payment_terms}) are shorter than "
                                f"company policy standard (Net {std_days})."
                            ),
                            citation=f"{pol.filename} (Page 1) & {inv.filename} (Page 1)",
                        )
                    )

            tol_pct = rules.get("variance_tolerance_pct")
            if tol_pct is not None and pos and inv.total_amount and pos[0].total_amount:
                var_pct = (
                    abs(inv.total_amount - pos[0].total_amount)
                    / max(pos[0].total_amount, 0.01)
                    * 100.0
                )
                if var_pct > float(tol_pct):
                    discrepancies.append(
                        DiscrepancyItem(
                            code="POLICY_VARIANCE_EXCEEDED",
                            category="policy_concern",
                            severity="critical",
                            field="variance_pct",
                            expected=f"<= {tol_pct}% variance ({pol.filename})",
                            actual=f"{var_pct:.1f}% variance",
                            potential_concern=(
                                f"Invoice-to-PO variance ({var_pct:.1f}%) exceeds the {tol_pct}% "
                                "policy variance tolerance and may require procurement hold."
                            ),
                            citation=f"{pol.filename} (Page 1)",
                        )
                    )

    # 4. Multi-contract clause comparison (flags Tier 3 reasoning for ambiguous legal conflicts)
    if len(contracts) >= 2:
        c_a, c_b = contracts[0], contracts[1]
        for clause_key in (
            "payment_terms",
            "liability_cap",
            "governing_law",
            "termination",
            "indemnification",
            "late_fee",
        ):
            val_a = c_a.contract_clauses.get(clause_key)
            val_b = c_b.contract_clauses.get(clause_key)
            if val_a and val_b and val_a.lower() != val_b.lower():
                requires_t3 = clause_key in {
                    "liability_cap",
                    "indemnification",
                    "governing_law",
                    "termination",
                }
                discrepancies.append(
                    DiscrepancyItem(
                        code=f"CONTRACT_CONFLICT_{clause_key.upper()}",
                        category="contract_conflict",
                        severity="critical" if requires_t3 else "high",
                        field=clause_key,
                        expected=f"{c_a.filename}: {val_a}",
                        actual=f"{c_b.filename}: {val_b}",
                        potential_concern=(
                            f"Conflicting '{clause_key.replace('_', ' ')}' language detected between "
                            f"{c_a.filename} and {c_b.filename}; precedence and legal impact require contextual interpretation."
                        ),
                        citation=f"{c_a.filename} (Page 1) vs {c_b.filename} (Page 1)",
                        requires_frontier_reasoning=requires_t3,
                    )
                )

    return discrepancies


@dataclass(slots=True)
class Tier0Result:
    handled: bool
    intent: str
    answer: str = ""
    extracted_fields: dict[str, Any] = field(default_factory=dict)
    citations: list[str] = field(default_factory=list)
    matched_rule: str = ""
    confidence: float = 0.0


def try_tier0_fast_path(query: str, documents: list[dict[str, Any]]) -> Tier0Result:
    """Attempt zero-LLM deterministic resolution for lookups, dates, and calculations."""
    if not documents:
        return Tier0Result(handled=False, intent="unknown")

    q = query.lower().strip()

    # Never shortcut multi-document comparison, policy compliance, or legal reasoning to Tier 0
    complex_signals = (
        "compare",
        "discrepanc",
        "policy",
        "follows",
        "conflict",
        "indemn",
        "ambiguous",
        "summarize",
        "classify",
        "recommend",
        "legal",
        "risk",
        "explain",
        "extract all",
        "structured",
    )
    if any(sig in q for sig in complex_signals):
        return Tier0Result(handled=False, intent="complex_deferred")

    records = [extract_structured_record(d) for d in documents]

    # 1. Invoice / PO number lookup
    if any(
        k in q
        for k in ("invoice number", "invoice #", "invoice no", "po number", "purchase order number")
    ):
        found = {}
        citations = []
        for r in records:
            if "po" in q or "purchase order" in q:
                val = r.document_number if r.doc_type == "purchase_order" else r.reference_po_number
                if val:
                    found[r.filename] = {"po_number": val}
                    citations.extend(r.citations)
            else:
                if r.document_number and (
                    r.doc_type == "invoice" or "inv" in r.document_number.lower()
                ):
                    found[r.filename] = {"invoice_number": r.document_number}
                    citations.extend(r.citations)
        if found:
            first_doc, fields = next(iter(found.items()))
            key, val = next(iter(fields.items()))
            return Tier0Result(
                handled=True,
                intent="deterministic_lookup",
                answer=f"The {key.replace('_', ' ')} in {first_doc} is **{val}**.",
                extracted_fields={"document_number": val, "matches": found},
                citations=citations,
                matched_rule="regex_document_number_lookup",
                confidence=1.0,
            )

    # 2. Date lookup (invoice date / due date / issue date / particular date)
    if any(
        k in q
        for k in (
            "due date",
            "invoice date",
            "issue date",
            "order date",
            "effective date",
            "what date",
            "date",
        )
    ):
        dates_found: dict[str, dict[str, str]] = {}
        citations = []
        for r in records:
            if r.key_dates:
                dates_found[r.filename] = dict(r.key_dates)
                citations.extend(r.citations)
        if dates_found:
            first_doc, dmap = next(iter(dates_found.items()))
            if "due" in q and "due_date" in dmap:
                ans = f"The due date in {first_doc} is **{dmap['due_date']}**."
                out_fields: dict[str, Any] = {"due_date": dmap["due_date"], "dates": dates_found}
            elif "issue_date" in dmap:
                ans = f"The invoice/issue date in {first_doc} is **{dmap['issue_date']}**."
                out_fields = {"issue_date": dmap["issue_date"], "dates": dates_found}
            else:
                k0, v0 = next(iter(dmap.items()))
                ans = f"Found {k0.replace('_', ' ')} in {first_doc}: **{v0}**."
                out_fields = {k0: v0, "dates": dates_found}
            return Tier0Result(
                handled=True,
                intent="deterministic_date_lookup",
                answer=ans,
                extracted_fields=out_fields,
                citations=citations,
                matched_rule="regex_date_parser",
                confidence=1.0,
            )

    # 3. Deterministic totals & expense calculations
    if any(
        k in q for k in ("total", "calculate", "sum", "expense", "amount due", "subtotal", "tax")
    ):
        totals: list[tuple[str, float, ExtractedDocumentRecord]] = []
        citations = []
        for r in records:
            if r.total_amount is not None:
                totals.append((r.filename, r.total_amount, r))
                citations.extend(r.citations)
        if totals:
            combined_total = round(sum(t[1] for t in totals), 2)
            if len(totals) == 1:
                fname, amt, rec = totals[0]
                parts = [f"The total amount in {fname} is **${amt:,.2f}**."]
                math_check = "not_applicable"
                if rec.subtotal is not None and rec.tax_amount is not None:
                    calc = round(rec.subtotal + rec.tax_amount, 2)
                    math_check = "passed" if abs(calc - amt) <= 0.02 else "mismatch"
                    parts.append(
                        f"Deterministic arithmetic check: Subtotal (${rec.subtotal:,.2f}) + "
                        f"Tax (${rec.tax_amount:,.2f}) = ${calc:,.2f} ({math_check})."
                    )
                return Tier0Result(
                    handled=True,
                    intent="deterministic_calculation",
                    answer=" ".join(parts),
                    extracted_fields={
                        "total_amount": amt,
                        "subtotal": rec.subtotal,
                        "tax_amount": rec.tax_amount,
                        "arithmetic_check": math_check,
                    },
                    citations=citations,
                    matched_rule="deterministic_currency_calculator",
                    confidence=1.0,
                )
            breakdown = {fname: amt for fname, amt, _ in totals}
            return Tier0Result(
                handled=True,
                intent="deterministic_calculation",
                answer=(
                    f"Calculated combined total across {len(totals)} document(s): "
                    f"**${combined_total:,.2f}**."
                ),
                extracted_fields={"combined_total": combined_total, "breakdown": breakdown},
                citations=citations,
                matched_rule="deterministic_multi_doc_sum",
                confidence=1.0,
            )

    # 4. Vendor or payment terms lookup
    if any(k in q for k in ("vendor", "supplier", "payment terms")):
        found_items: dict[str, Any] = {}
        citations = []
        for r in records:
            if "payment terms" in q and r.payment_terms:
                found_items[r.filename] = {"payment_terms": r.payment_terms}
                citations.extend(r.citations)
            elif ("vendor" in q or "supplier" in q) and r.vendor:
                found_items[r.filename] = {"vendor": r.vendor}
                citations.extend(r.citations)
        if found_items:
            fname, fdict = next(iter(found_items.items()))
            k, v = next(iter(fdict.items()))
            return Tier0Result(
                handled=True,
                intent="deterministic_lookup",
                answer=f"The {k.replace('_', ' ')} in {fname} is **{v}**.",
                extracted_fields={k: v, "matches": found_items},
                citations=citations,
                matched_rule=f"regex_{k}_lookup",
                confidence=1.0,
            )

    return Tier0Result(handled=False, intent="needs_ai_routing")
