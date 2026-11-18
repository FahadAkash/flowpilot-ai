"""PyMuPDF-powered document parser with structured page extraction."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf


@dataclass(slots=True)
class ParsedPage:
    page_number: int
    text: str
    headings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParsedDocument:
    filename: str
    content_type: str
    sha256: str
    page_count: int
    size_bytes: int
    raw_text: str
    pages: list[ParsedPage]
    inferred_doc_type: str
    metadata: dict[str, Any] = field(default_factory=dict)


DOC_TYPE_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("invoice", ("invoice", "inv-", "bill to", "amount due", "remit to", "tax invoice")),
    (
        "purchase_order",
        ("purchase order", "po-", "p.o.", "ship to", "authorized buyer", "requisition"),
    ),
    (
        "policy",
        (
            "company policy",
            "procurement policy",
            "approval threshold",
            "expense policy",
            "compliance policy",
        ),
    ),
    (
        "contract",
        (
            "agreement",
            "indemnification",
            "governing law",
            "termination",
            "whereas",
            "liability cap",
            "confidentiality",
        ),
    ),
    (
        "financial_report",
        (
            "balance sheet",
            "income statement",
            "ebitda",
            "fiscal quarter",
            "revenue",
            "operating margin",
        ),
    ),
    (
        "healthcare_report",
        ("patient", "diagnosis", "clinical", "discharge summary", "icd-", "vital signs"),
    ),
]


def infer_document_type(filename: str, text: str) -> str:
    """Fast heuristic classification used during ingestion (refined by Tier 1 when ambiguous)."""
    haystack = f"{filename.lower()}\n{text[:4000].lower()}"
    best_type = "general_document"
    best_score = 0
    for doc_type, keywords in DOC_TYPE_PATTERNS:
        score = sum(1 for kw in keywords if kw in haystack)
        if doc_type.replace("_", "") in filename.lower().replace("_", "").replace("-", ""):
            score += 2
        if score > best_score:
            best_score = score
            best_type = doc_type
    return best_type


def _extract_headings(text: str) -> list[str]:
    headings: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or len(stripped) > 90:
            continue
        if (
            re.match(r"^(SECTION|ARTICLE|CLAUSE|\d+\.)\s+", stripped, re.IGNORECASE)
            or (stripped.isupper() and len(stripped) >= 4)
            or stripped.endswith(":")
        ):
            headings.append(stripped.rstrip(":"))
    return headings[:12]


def parse_document_bytes(
    data: bytes,
    *,
    filename: str,
    content_type: str = "application/pdf",
) -> ParsedDocument:
    """Parse PDF (via PyMuPDF) or plain-text documents into page-indexed text."""
    digest = hashlib.sha256(data).hexdigest()
    suffix = Path(filename).suffix.lower()
    is_pdf = suffix == ".pdf" or "pdf" in content_type.lower() or data[:4] == b"%PDF"

    pages: list[ParsedPage] = []
    metadata: dict[str, Any] = {"parser": "pymupdf" if is_pdf else "text"}

    if is_pdf:
        with pymupdf.open(stream=data, filetype="pdf") as pdf_doc:
            pdf_meta = pdf_doc.metadata or {}
            metadata["pdf_title"] = pdf_meta.get("title") or ""
            metadata["pdf_author"] = pdf_meta.get("author") or ""
            for idx, page in enumerate(pdf_doc, start=1):
                page_text = page.get_text("text").strip()
                pages.append(
                    ParsedPage(
                        page_number=idx,
                        text=page_text,
                        headings=_extract_headings(page_text),
                    )
                )
    else:
        decoded = data.decode("utf-8", errors="replace").strip()
        raw_pages = [p.strip() for p in decoded.split("\f")] if "\f" in decoded else [decoded]
        for idx, page_text in enumerate(raw_pages, start=1):
            pages.append(
                ParsedPage(
                    page_number=idx,
                    text=page_text,
                    headings=_extract_headings(page_text),
                )
            )

    if not pages:
        pages.append(ParsedPage(page_number=1, text="", headings=[]))

    raw_text = "\n\n".join(f"[Page {p.page_number}]\n{p.text}" for p in pages if p.text).strip()
    inferred = infer_document_type(filename, raw_text)
    metadata["inferred_doc_type"] = inferred
    metadata["char_count"] = len(raw_text)

    return ParsedDocument(
        filename=filename,
        content_type=content_type,
        sha256=digest,
        page_count=len(pages),
        size_bytes=len(data),
        raw_text=raw_text,
        pages=pages,
        inferred_doc_type=inferred,
        metadata=metadata,
    )
