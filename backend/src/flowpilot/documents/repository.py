"""Document persistence and hybrid pgvector + lexical retrieval repository."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from flowpilot.config import get_settings
from flowpilot.db.models import Document, DocumentChunk
from flowpilot.documents.chunker import chunk_parsed_document
from flowpilot.documents.embeddings import cosine_similarity, embed_text, lexical_overlap_score
from flowpilot.documents.parser import parse_document_bytes
from flowpilot.schemas.documents import RetrievedChunk


class DocumentRepository:
    """Service/Repository owning document ingestion, storage, and hybrid vector search."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()

    async def ingest_bytes(
        self,
        *,
        user_id: str,
        filename: str,
        data: bytes,
        content_type: str = "application/pdf",
    ) -> Document:
        """Parse, store, chunk, embed, and persist a document (deduplicating per user+sha256)."""
        parsed = parse_document_bytes(data, filename=filename, content_type=content_type)

        existing_res = await self.session.execute(
            select(Document).where(
                Document.user_id == user_id,
                Document.sha256 == parsed.sha256,
                Document.filename == filename,
            )
        )
        existing = existing_res.scalar_one_or_none()
        if existing is not None:
            return existing

        safe_name = Path(filename).name.replace("..", "_")
        storage_file = self.settings.storage_path / f"{parsed.sha256[:12]}_{safe_name}"
        storage_file.write_bytes(data)

        doc = Document(
            user_id=user_id,
            filename=filename,
            content_type=content_type,
            sha256=parsed.sha256,
            doc_type=parsed.inferred_doc_type,
            page_count=parsed.page_count,
            size_bytes=parsed.size_bytes,
            storage_path=str(storage_file),
            raw_text=parsed.raw_text,
            metadata_json=parsed.metadata,
            status="ready",
        )
        self.session.add(doc)
        await self.session.flush()

        chunks = chunk_parsed_document(parsed)
        for ch in chunks:
            embedding = embed_text(ch.content, dim=self.settings.embedding_dimensions)
            self.session.add(
                DocumentChunk(
                    document_id=doc.id,
                    chunk_index=ch.chunk_index,
                    page_number=ch.page_number,
                    section_title=ch.section_title,
                    content=ch.content,
                    token_count=ch.token_count,
                    embedding=embedding,
                    metadata_json={"filename": filename, "doc_type": doc.doc_type},
                )
            )

        await self.session.commit()
        await self.session.refresh(doc)
        return doc

    async def list_documents(self, *, user_id: str) -> list[tuple[Document, int]]:
        stmt = (
            select(Document, func.count(DocumentChunk.id))
            .outerjoin(DocumentChunk, DocumentChunk.document_id == Document.id)
            .where(Document.user_id == user_id)
            .group_by(Document.id)
            .order_by(Document.created_at.desc())
        )
        rows = (await self.session.execute(stmt)).all()
        return [(row[0], int(row[1])) for row in rows]

    async def get_documents_by_ids(
        self,
        *,
        user_id: str,
        document_ids: list[str],
    ) -> list[Document]:
        if not document_ids:
            stmt = (
                select(Document)
                .where(Document.user_id == user_id)
                .order_by(Document.created_at.desc())
            )
        else:
            stmt = select(Document).where(
                Document.user_id == user_id,
                Document.id.in_(document_ids),
            )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_document_with_chunks(
        self,
        *,
        user_id: str,
        document_id: str,
    ) -> tuple[Document | None, list[DocumentChunk]]:
        doc_res = await self.session.execute(
            select(Document).where(Document.id == document_id, Document.user_id == user_id)
        )
        doc = doc_res.scalar_one_or_none()
        if doc is None:
            return None, []
        chunk_res = await self.session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == doc.id)
            .order_by(DocumentChunk.chunk_index.asc())
        )
        return doc, list(chunk_res.scalars().all())

    async def delete_document(self, *, user_id: str, document_id: str) -> bool:
        doc_res = await self.session.execute(
            select(Document).where(Document.id == document_id, Document.user_id == user_id)
        )
        doc = doc_res.scalar_one_or_none()
        if doc is None:
            return False
        await self.session.delete(doc)
        await self.session.commit()
        return True

    async def hybrid_search(
        self,
        *,
        query: str,
        document_ids: list[str],
        top_k: int = 8,
    ) -> list[RetrievedChunk]:
        """Hybrid vector + lexical search across chunks (uses pgvector ordering on Postgres)."""
        if not document_ids:
            return []

        q_vec = embed_text(query, dim=self.settings.embedding_dimensions)
        bind = self.session.get_bind()
        is_pg = bind is not None and bind.dialect.name == "postgresql"

        if is_pg:
            stmt = (
                select(DocumentChunk, Document)
                .join(Document, DocumentChunk.document_id == Document.id)
                .where(DocumentChunk.document_id.in_(document_ids))
                .order_by(DocumentChunk.embedding.cosine_distance(q_vec))
                .limit(top_k * 2)
            )
        else:
            stmt = (
                select(DocumentChunk, Document)
                .join(Document, DocumentChunk.document_id == Document.id)
                .where(DocumentChunk.document_id.in_(document_ids))
            )

        rows = (await self.session.execute(stmt)).all()
        scored: list[RetrievedChunk] = []
        for chunk, doc in rows:
            vec_score = cosine_similarity(q_vec, chunk.embedding)
            lex_score = lexical_overlap_score(query, chunk.content)
            combined = round(0.60 * vec_score + 0.40 * lex_score, 4)
            scored.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=doc.id,
                    filename=doc.filename,
                    doc_type=doc.doc_type,
                    page_number=chunk.page_number,
                    section_title=chunk.section_title,
                    content=chunk.content,
                    score=combined,
                )
            )

        scored.sort(key=lambda c: c.score, reverse=True)
        # Ensure multi-document representation so no uploaded document is starved
        selected: list[RetrievedChunk] = []
        seen_ids: set[str] = set()
        seen_docs: set[str] = set()
        for item in scored:
            if item.document_id not in seen_docs and len(selected) < top_k:
                selected.append(item)
                seen_ids.add(item.chunk_id)
                seen_docs.add(item.document_id)
        for item in scored:
            if len(selected) >= top_k:
                break
            if item.chunk_id not in seen_ids:
                selected.append(item)
                seen_ids.add(item.chunk_id)
        return selected

    async def serialize_documents_for_state(
        self, documents: list[Document]
    ) -> list[dict[str, Any]]:
        """Serialize ORM Document rows into raw dicts for LangGraph FlowPilotState."""
        return [
            {
                "id": d.id,
                "filename": d.filename,
                "doc_type": d.doc_type,
                "sha256": d.sha256,
                "page_count": d.page_count,
                "raw_text": d.raw_text,
                "metadata": d.metadata_json,
            }
            for d in documents
        ]
