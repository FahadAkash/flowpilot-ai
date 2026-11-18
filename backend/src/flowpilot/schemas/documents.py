"""Pydantic v2 schemas for document ingestion and retrieval."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    chunk_index: int
    page_number: int
    section_title: str
    content: str
    token_count: int
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    content_type: str
    sha256: str
    doc_type: str
    page_count: int
    size_bytes: int
    status: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    chunk_count: int = 0


class DocumentDetailOut(DocumentOut):
    raw_text: str
    chunks: list[DocumentChunkOut] = Field(default_factory=list)


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    doc_type: str
    page_number: int
    section_title: str
    content: str
    score: float
