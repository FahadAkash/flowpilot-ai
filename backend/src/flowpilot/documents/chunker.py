"""Structure-aware document chunking and shared token-budget context limiter.

Follows python-skills/llm-features:
- Single shared `fit_context` limiter budgeted in tokens, called at every prompt boundary.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from flowpilot.documents.parser import ParsedDocument

TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def estimate_tokens(text: str) -> int:
    """Fast, language-aware token count approximation (~1.3x words/punctuation tokens)."""
    if not text:
        return 0
    raw_units = len(TOKEN_PATTERN.findall(text))
    return max(1, math.ceil(raw_units * 1.15))


def fit_context(text: str, *, max_tokens: int) -> str:
    """Single shared context limiter budgeted in tokens (never raw character slicing)."""
    if max_tokens <= 0 or not text:
        return ""
    if estimate_tokens(text) <= max_tokens:
        return text

    allowed_units = max(1, int(max_tokens / 1.15))
    # Preserve document head (70%) and tail (30%) so totals/signatures aren't lost
    head_count = int(allowed_units * 0.70)
    tail_count = max(1, allowed_units - head_count)

    # Map token boundaries back to original string indices cleanly
    matches = list(TOKEN_PATTERN.finditer(text))
    if len(matches) <= allowed_units:
        return text
    head_end = matches[min(head_count - 1, len(matches) - 1)].end()
    tail_start = matches[max(0, len(matches) - tail_count)].start()
    if head_end >= tail_start:
        return text[:head_end]
    return f"{text[:head_end].rstrip()}\n\n[... context truncated to {max_tokens} token budget ...]\n\n{text[tail_start:].lstrip()}"


@dataclass(slots=True)
class ChunkDraft:
    chunk_index: int
    page_number: int
    section_title: str
    content: str
    token_count: int


def chunk_parsed_document(
    parsed: ParsedDocument,
    *,
    target_tokens: int = 320,
    overlap_tokens: int = 40,
) -> list[ChunkDraft]:
    """Split a parsed document into section-aware overlapping chunks."""
    chunks: list[ChunkDraft] = []
    chunk_idx = 0

    for page in parsed.pages:
        if not page.text.strip():
            continue
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", page.text) if p.strip()]
        current_section = page.headings[0] if page.headings else f"Page {page.page_number}"
        buffer: list[str] = []
        buffer_tokens = 0

        for para in paragraphs:
            first_line = para.splitlines()[0].strip()
            if len(first_line) <= 80 and (
                re.match(r"^(SECTION|ARTICLE|CLAUSE|\d+\.)\s+", first_line, re.IGNORECASE)
                or first_line.isupper()
            ):
                current_section = first_line.rstrip(":")

            para_tokens = estimate_tokens(para)
            if buffer and buffer_tokens + para_tokens > target_tokens:
                content = "\n\n".join(buffer)
                chunks.append(
                    ChunkDraft(
                        chunk_index=chunk_idx,
                        page_number=page.page_number,
                        section_title=current_section,
                        content=content,
                        token_count=estimate_tokens(content),
                    )
                )
                chunk_idx += 1
                # Retain trailing overlap paragraph if small enough
                if buffer and estimate_tokens(buffer[-1]) <= overlap_tokens * 2:
                    buffer = [buffer[-1], para]
                    buffer_tokens = estimate_tokens(buffer[0]) + para_tokens
                else:
                    buffer = [para]
                    buffer_tokens = para_tokens
            else:
                buffer.append(para)
                buffer_tokens += para_tokens

        if buffer:
            content = "\n\n".join(buffer)
            chunks.append(
                ChunkDraft(
                    chunk_index=chunk_idx,
                    page_number=page.page_number,
                    section_title=current_section,
                    content=content,
                    token_count=estimate_tokens(content),
                )
            )
            chunk_idx += 1

    return chunks
