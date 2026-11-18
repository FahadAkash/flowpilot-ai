"""Reproducible multi-domain PDF corpus (UniDoc-Bench task categories) + JSONL loader.

Generates genuine PDF documents via ReportLab (parsed end-to-end with PyMuPDF) covering:
- Invoices, Purchase Orders, Company Policies, Commercial Contracts,
  Financial Reports, and Healthcare Summaries
- Positive AND negative compliance cases (following python-skills/llm-features)
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def render_text_to_pdf_bytes(title: str, lines: list[str]) -> bytes:
    """Render structured multi-line document text into valid PDF bytes."""
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=letter)
    pdf.setTitle(title)
    y = 750
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(50, y, title)
    y -= 26
    pdf.setFont("Helvetica", 10)
    for line in lines:
        if y < 60:
            pdf.showPage()
            pdf.setFont("Helvetica", 10)
            y = 750
        pdf.drawString(50, y, line[:105])
        y -= 15
    pdf.save()
    return buf.getvalue()


@dataclass(slots=True)
class DemoDocumentSpec:
    filename: str
    doc_type: str
    title: str
    lines: list[str]

    def to_pdf_bytes(self) -> bytes:
        return render_text_to_pdf_bytes(self.title, self.lines)

    def to_state_dict(self, doc_id: str) -> dict[str, Any]:
        text = f"[Page 1]\n{self.title}\n" + "\n".join(self.lines)
        return {
            "id": doc_id,
            "filename": self.filename,
            "doc_type": self.doc_type,
            "sha256": f"bench-{doc_id}",
            "page_count": 1,
            "raw_text": text,
            "metadata": {"source": "unidoc-bench-curated"},
        }


@dataclass(slots=True)
class BenchmarkCase:
    case_id: str
    category: str
    expected_tier: int
    query: str
    documents: list[DemoDocumentSpec]
    ground_truth_fields: dict[str, Any] = field(default_factory=dict)
    ground_truth_doc_type: str | None = None
    ground_truth_discrepancy_codes: list[str] = field(default_factory=list)
    expect_escalation: bool = False


def get_enterprise_demo_pack() -> list[DemoDocumentSpec]:
    """Curated 5-PDF Enterprise Demo Pack matching the FlowPilot flagship workflow."""
    return [
        DemoDocumentSpec(
            filename="Invoice_INV-2026-8841.pdf",
            doc_type="invoice",
            title="TAX INVOICE — APEX CLOUD INFRASTRUCTURE INC.",
            lines=[
                "Invoice Number: INV-2026-8841",
                "Purchase Order Reference: PO-2026-4410",
                "Vendor: Apex Cloud Infrastructure Inc.",
                "Buyer: Meridian Enterprise Holdings",
                "Invoice Date: 2026-10-14",
                "Due Date: 2026-10-29",
                "Payment Terms: Net 15",
                "LINE ITEMS:",
                "- Enterprise GPU Cluster Node | Qty: 6 x $1,850.00 = $11,100.00",
                "- Managed Vector DB Storage | Qty: 2 x $1,200.00 = $2,400.00",
                "- Priority Support SLA | Qty: 1 x $1,100.00 = $1,100.00",
                "Subtotal: $14,600.00",
                "Tax (8%): $1,168.00",
                "Grand Total: $15,768.00",
            ],
        ),
        DemoDocumentSpec(
            filename="PurchaseOrder_PO-2026-4410.pdf",
            doc_type="purchase_order",
            title="AUTHORIZED PURCHASE ORDER — MERIDIAN ENTERPRISE HOLDINGS",
            lines=[
                "Purchase Order Number: PO-2026-4410",
                "Vendor: Apex Cloud Infrastructure Inc.",
                "Buyer: Meridian Enterprise Holdings",
                "Order Date: 2026-10-01",
                "Payment Terms: Net 30",
                "AUTHORIZED LINE ITEMS:",
                "- Enterprise GPU Cluster Node | Qty: 5 x $1,750.00 = $8,750.00",
                "- Managed Vector DB Storage | Qty: 2 x $1,200.00 = $2,400.00",
                "- Priority Support SLA | Qty: 1 x $1,100.00 = $1,100.00",
                "Subtotal: $12,250.00",
                "Tax (8%): $980.00",
                "Total Authorized: $13,230.00",
            ],
        ),
        DemoDocumentSpec(
            filename="CompanyPolicy_Procurement_v4.pdf",
            doc_type="policy",
            title="MERIDIAN ENTERPRISE PROCUREMENT & ACCOUNTS PAYABLE POLICY v4.2",
            lines=[
                "Effective Date: 2026-01-01",
                "SECTION 1: APPROVAL THRESHOLDS",
                "Auto-approval without VP approval is capped at a single invoice limit of $10,000.00.",
                "Any invoice above $10,000.00 requires documented VP approval or CFO approval.",
                "SECTION 2: PRICE AND AMOUNT VARIANCE",
                "Maximum allowable invoice-to-PO price variance tolerance is 5%.",
                "Invoices exceeding 5% variance must be placed on procurement hold.",
                "SECTION 3: PAYMENT TERMS",
                "Standard payment terms require minimum Net 30 from receipt of valid invoice.",
                "Approved Vendors: Apex Cloud Infrastructure Inc., Northstar Analytics LLC, Orion BioLabs",
            ],
        ),
        DemoDocumentSpec(
            filename="MasterServicesAgreement_A.pdf",
            doc_type="contract",
            title="MASTER SERVICES AGREEMENT (CONTRACT CTR-2026-MSA-01)",
            lines=[
                "Contract ID: CTR-2026-MSA-01",
                "Effective Date: 2026-03-01",
                "Vendor: Apex Cloud Infrastructure Inc.",
                "Buyer: Meridian Enterprise Holdings",
                "CLAUSE 1 - PAYMENT TERMS: Buyer shall remit payment within Net 45 days of invoice receipt.",
                "CLAUSE 2 - LIABILITY CAP: Aggregate liability under this Agreement is capped at 12 months of fees paid.",
                "CLAUSE 3 - INDEMNIFICATION: Vendor provides uncapped mutual indemnification for IP and data breaches.",
                "CLAUSE 4 - GOVERNING LAW: Governed exclusively by the laws of the State of Delaware.",
                "CLAUSE 5 - TERMINATION: Either party may terminate for convenience with 60 days written notice.",
            ],
        ),
        DemoDocumentSpec(
            filename="OrderFormAddendum_B.pdf",
            doc_type="contract",
            title="ENTERPRISE ORDER FORM ADDENDUM (CONTRACT CTR-2026-ADD-02)",
            lines=[
                "Contract ID: CTR-2026-ADD-02",
                "Effective Date: 2026-09-15",
                "Vendor: Apex Cloud Infrastructure Inc.",
                "Buyer: Meridian Enterprise Holdings",
                "CLAUSE 1 - PAYMENT TERMS: All invoices under this Addendum are due Net 15 with 2% monthly late fee.",
                "CLAUSE 2 - LIABILITY CAP: Aggregate liability is strictly capped at $25,000 regardless of fees paid.",
                "CLAUSE 3 - INDEMNIFICATION: Vendor excludes consequential damages and caps indemnification at $50,000.",
                "CLAUSE 4 - GOVERNING LAW: Any dispute shall be resolved under New York law and arbitration.",
                "CLAUSE 5 - TERMINATION: Non-cancellable 24-month commitment with no termination for convenience.",
            ],
        ),
    ]


def build_benchmark_suite(*, include_stress_cases: bool = True) -> list[BenchmarkCase]:
    """Build a balanced 16-case multi-domain UniDoc-Bench-inspired evaluation suite.

    Distribution mirrors realistic enterprise document workloads:
    - ~38% Tier 0 deterministic lookups/calculations
    - ~25% Tier 1 lightweight classification/extraction
    - ~25% Tier 2 multi-document 2-way/3-way compliance comparisons (positive + negative)
    - ~12% Tier 3 complex conflicting legal contract reasoning
    """
    demo = {d.filename: d for d in get_enterprise_demo_pack()}
    inv_disc = demo["Invoice_INV-2026-8841.pdf"]
    po_disc = demo["PurchaseOrder_PO-2026-4410.pdf"]
    policy = demo["CompanyPolicy_Procurement_v4.pdf"]
    contract_a = demo["MasterServicesAgreement_A.pdf"]
    contract_b = demo["OrderFormAddendum_B.pdf"]

    # Compliant (negative discrepancy) pair to verify low false-positive rate
    inv_clean = DemoDocumentSpec(
        filename="Invoice_INV-2026-5002.pdf",
        doc_type="invoice",
        title="INVOICE — NORTHSTAR ANALYTICS LLC",
        lines=[
            "Invoice Number: INV-2026-5002",
            "Purchase Order Reference: PO-2026-3002",
            "Vendor: Northstar Analytics LLC",
            "Buyer: Meridian Enterprise Holdings",
            "Invoice Date: 2026-11-01",
            "Due Date: 2026-12-01",
            "Payment Terms: Net 30",
            "- Data Pipeline Audit | Qty: 4 x $1,500.00 = $6,000.00",
            "Subtotal: $6,000.00",
            "Tax (5%): $300.00",
            "Grand Total: $6,300.00",
        ],
    )
    po_clean = DemoDocumentSpec(
        filename="PurchaseOrder_PO-2026-3002.pdf",
        doc_type="purchase_order",
        title="PURCHASE ORDER — NORTHSTAR ANALYTICS LLC",
        lines=[
            "Purchase Order Number: PO-2026-3002",
            "Vendor: Northstar Analytics LLC",
            "Buyer: Meridian Enterprise Holdings",
            "Order Date: 2026-10-20",
            "Payment Terms: Net 30",
            "- Data Pipeline Audit | Qty: 4 x $1,500.00 = $6,000.00",
            "Subtotal: $6,000.00",
            "Tax (5%): $300.00",
            "Total Authorized: $6,300.00",
        ],
    )
    fin_report = DemoDocumentSpec(
        filename="Q3_2026_Financial_Report.pdf",
        doc_type="financial_report",
        title="MERIDIAN HOLDINGS Q3 2026 QUARTERLY FINANCIAL REPORT",
        lines=[
            "Effective Date: 2026-10-15",
            "Fiscal Quarter: Q3 2026",
            "Total Revenue: $48,200,000.00",
            "Operating Margin: 24.5%",
            "EBITDA: $11,809,000.00",
            "Subtotal: $48,200,000.00",
            "Grand Total: $48,200,000.00",
        ],
    )
    health_report = DemoDocumentSpec(
        filename="Clinical_Discharge_Summary_441.pdf",
        doc_type="healthcare_report",
        title="CLINICAL DISCHARGE SUMMARY — METRO GENERAL HOSPITAL",
        lines=[
            "Effective Date: 2026-09-28",
            "Patient: Redacted Case #441",
            "Diagnosis: Community-acquired pneumonia (ICD-10 J18.9), resolved.",
            "Vital Signs: Stable, afebrile, SpO2 98% on room air.",
            "Follow-up recommended in 14 days with primary care physician.",
        ],
    )
    inv_math_err = DemoDocumentSpec(
        filename="Invoice_INV-2026-9099.pdf",
        doc_type="invoice",
        title="INVOICE — ORION BIOLABS",
        lines=[
            "Invoice Number: INV-2026-9099",
            "Vendor: Orion BioLabs",
            "Invoice Date: 2026-11-05",
            "Due Date: 2026-12-05",
            "Payment Terms: Net 30",
            "- Diagnostic Reagent Kit | Qty: 10 x $400.00 = $4,000.00",
            "Subtotal: $4,000.00",
            "Tax (10%): $400.00",
            "Grand Total: $4,750.00",  # Intentional $350 arithmetic error
        ],
    )

    cases: list[BenchmarkCase] = [
        # --- Tier 0 Deterministic Fast Path (6 cases) ---
        BenchmarkCase(
            case_id="t0-invoice-number",
            category="tier0_lookup",
            expected_tier=0,
            query="What is the invoice number?",
            documents=[inv_disc],
            ground_truth_fields={"document_number": "INV-2026-8841"},
        ),
        BenchmarkCase(
            case_id="t0-invoice-date",
            category="tier0_date",
            expected_tier=0,
            query="What is the invoice date?",
            documents=[inv_disc],
            ground_truth_fields={"issue_date": "2026-10-14"},
        ),
        BenchmarkCase(
            case_id="t0-due-date",
            category="tier0_date",
            expected_tier=0,
            query="Find the payment due date in this invoice.",
            documents=[inv_clean],
            ground_truth_fields={"due_date": "2026-12-01"},
        ),
        BenchmarkCase(
            case_id="t0-calc-single-total",
            category="tier0_calculation",
            expected_tier=0,
            query="Calculate the invoice total and verify subtotal plus tax.",
            documents=[inv_clean],
            ground_truth_fields={"total_amount": 6300.0, "arithmetic_check": "passed"},
        ),
        BenchmarkCase(
            case_id="t0-calc-multi-expenses",
            category="tier0_calculation",
            expected_tier=0,
            query="Calculate total expenses across these invoices.",
            documents=[inv_disc, inv_clean],
            ground_truth_fields={"combined_total": 22068.0},
        ),
        BenchmarkCase(
            case_id="t0-vendor-lookup",
            category="tier0_lookup",
            expected_tier=0,
            query="Who is the vendor listed on this purchase order?",
            documents=[po_clean],
            ground_truth_fields={"vendor": "Northstar Analytics LLC"},
        ),
        # --- Tier 1 Lightweight AI (4 cases) ---
        BenchmarkCase(
            case_id="t1-classify-invoice",
            category="tier1_classification",
            expected_tier=1,
            query="Classify whether this document is an invoice, contract, or policy.",
            documents=[inv_disc],
            ground_truth_doc_type="invoice",
        ),
        BenchmarkCase(
            case_id="t1-classify-financial",
            category="tier1_classification",
            expected_tier=1,
            query="What type of document is this?",
            documents=[fin_report],
            ground_truth_doc_type="financial_report",
        ),
        BenchmarkCase(
            case_id="t1-classify-healthcare",
            category="tier1_classification",
            expected_tier=1,
            query="Classify this document type and summarize key points.",
            documents=[health_report],
            ground_truth_doc_type="healthcare_report",
        ),
        BenchmarkCase(
            case_id="t1-extract-entities",
            category="tier1_extraction",
            expected_tier=1,
            query="Extract all structured invoice fields including vendor, date, terms, and total.",
            documents=[inv_clean],
            ground_truth_fields={
                "document_number": "INV-2026-5002",
                "vendor": "Northstar Analytics LLC",
                "total_amount": 6300.0,
                "payment_terms": "Net 30",
            },
        ),
        # --- Tier 2 Multi-Agent Specialist Workflow (4 cases: positive + negative) ---
        BenchmarkCase(
            case_id="t2-3way-discrepancy",
            category="tier2_comparison",
            expected_tier=2,
            query="Check whether this invoice follows our purchase order and company policy. Identify any discrepancies.",
            documents=[inv_disc, po_disc, policy],
            ground_truth_discrepancy_codes=[
                "INV_PO_TOTAL_MISMATCH",
                "INV_PO_TERMS_MISMATCH",
                "LINE_QTY_MISMATCH",
                "LINE_PRICE_MISMATCH",
                "POLICY_APPROVAL_THRESHOLD",
                "POLICY_PAYMENT_TERMS_CONCERN",
                "POLICY_VARIANCE_EXCEEDED",
            ],
        ),
        BenchmarkCase(
            case_id="t2-3way-clean-compliant",
            category="tier2_comparison_negative",
            expected_tier=2,
            query="Check whether this invoice follows our purchase order and company policy. Identify any discrepancies.",
            documents=[inv_clean, po_clean, policy],
            ground_truth_discrepancy_codes=[],
        ),
        BenchmarkCase(
            case_id="t2-2way-po-match",
            category="tier2_comparison",
            expected_tier=2,
            query="Compare the invoice line items and totals against the purchase order.",
            documents=[inv_disc, po_disc],
            ground_truth_discrepancy_codes=[
                "INV_PO_TOTAL_MISMATCH",
                "INV_PO_TERMS_MISMATCH",
                "LINE_QTY_MISMATCH",
                "LINE_PRICE_MISMATCH",
            ],
        ),
        BenchmarkCase(
            case_id="t2-arithmetic-audit",
            category="tier2_audit",
            expected_tier=2,
            query="Audit this invoice against company policy and check for calculation discrepancies.",
            documents=[inv_math_err, policy],
            ground_truth_discrepancy_codes=["INV_ARITHMETIC_MISMATCH"],
        ),
        # --- Tier 3 Frontier Escalation (2 cases) ---
        BenchmarkCase(
            case_id="t3-contract-conflicts",
            category="tier3_legal_reasoning",
            expected_tier=3,
            query="Compare these two contracts and resolve conflicting indemnification, liability cap, and payment terms.",
            documents=[contract_a, contract_b],
            ground_truth_discrepancy_codes=[
                "CONTRACT_CONFLICT_PAYMENT_TERMS",
                "CONTRACT_CONFLICT_LIABILITY_CAP",
                "CONTRACT_CONFLICT_GOVERNING_LAW",
                "CONTRACT_CONFLICT_TERMINATION",
                "CONTRACT_CONFLICT_INDEMNIFICATION",
            ],
            expect_escalation=True,
        ),
        BenchmarkCase(
            case_id="t3-contract-governing-law",
            category="tier3_legal_reasoning",
            expected_tier=3,
            query="Identify ambiguous legal conflicts between the Master Services Agreement and Addendum regarding governing law and liability cap.",
            documents=[contract_a, contract_b],
            ground_truth_discrepancy_codes=[
                "CONTRACT_CONFLICT_PAYMENT_TERMS",
                "CONTRACT_CONFLICT_LIABILITY_CAP",
                "CONTRACT_CONFLICT_GOVERNING_LAW",
                "CONTRACT_CONFLICT_TERMINATION",
                "CONTRACT_CONFLICT_INDEMNIFICATION",
            ],
            expect_escalation=True,
        ),
    ]

    if not include_stress_cases:
        return cases[:12]
    return cases


def load_unidoc_bench_jsonl(jsonl_path: Path) -> list[BenchmarkCase]:
    """Import external UniDoc-Bench JSONL records into FlowPilot BenchmarkCase format."""
    cases: list[BenchmarkCase] = []
    for idx, line in enumerate(jsonl_path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        row = json.loads(line)
        docs = [
            DemoDocumentSpec(
                filename=str(d.get("filename", f"unidoc_{idx}_{j}.pdf")),
                doc_type=str(d.get("doc_type", "general_document")),
                title=str(d.get("title", f"Document {j + 1}")),
                lines=str(d.get("text", "")).splitlines(),
            )
            for j, d in enumerate(row.get("documents", []))
        ]
        cases.append(
            BenchmarkCase(
                case_id=str(row.get("id", f"unidoc-{idx}")),
                category=str(row.get("task_type", "unidoc_qa")),
                expected_tier=int(row.get("expected_tier", 1)),
                query=str(row.get("question") or row.get("query") or ""),
                documents=docs,
                ground_truth_fields=dict(row.get("ground_truth_fields") or {}),
                ground_truth_doc_type=row.get("ground_truth_doc_type"),
                ground_truth_discrepancy_codes=list(
                    row.get("ground_truth_discrepancy_codes") or []
                ),
                expect_escalation=bool(row.get("expect_escalation", False)),
            )
        )
    return cases
