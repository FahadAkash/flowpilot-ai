"""Document upload, demo pack loading, listing, chunk inspection, and deletion routes."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from flowpilot.api.deps import CurrentUserDep, SessionDep
from flowpilot.benchmarks.dataset import get_enterprise_demo_pack
from flowpilot.documents.repository import DocumentRepository
from flowpilot.schemas.documents import DocumentChunkOut, DocumentDetailOut, DocumentOut

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


@router.post("/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    user: CurrentUserDep,
    session: SessionDep,
    file: UploadFile = File(...),
) -> DocumentOut:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded file exceeds 20 MB size limit.")

    repo = DocumentRepository(session)
    doc = await repo.ingest_bytes(
        user_id=user.id,
        filename=file.filename or "uploaded_document.pdf",
        data=data,
        content_type=file.content_type or "application/pdf",
    )
    _, chunks = await repo.get_document_with_chunks(user_id=user.id, document_id=doc.id)
    out = DocumentOut.model_validate(doc)
    out.chunk_count = len(chunks)
    return out


@router.post("/demo-pack", response_model=list[DocumentOut])
async def load_enterprise_demo_pack(
    user: CurrentUserDep,
    session: SessionDep,
) -> list[DocumentOut]:
    """Generate and ingest the 5-PDF Enterprise Demo Pack (Invoice, PO, Policy, 2 Contracts)."""
    repo = DocumentRepository(session)
    results: list[DocumentOut] = []
    for spec in get_enterprise_demo_pack():
        doc = await repo.ingest_bytes(
            user_id=user.id,
            filename=spec.filename,
            data=spec.to_pdf_bytes(),
            content_type="application/pdf",
        )
        _, chunks = await repo.get_document_with_chunks(user_id=user.id, document_id=doc.id)
        out = DocumentOut.model_validate(doc)
        out.chunk_count = len(chunks)
        results.append(out)
    return results


@router.get("", response_model=list[DocumentOut])
async def list_documents(user: CurrentUserDep, session: SessionDep) -> list[DocumentOut]:
    repo = DocumentRepository(session)
    rows = await repo.list_documents(user_id=user.id)
    out: list[DocumentOut] = []
    for doc, chunk_count in rows:
        item = DocumentOut.model_validate(doc)
        item.chunk_count = chunk_count
        out.append(item)
    return out


@router.get("/{document_id}", response_model=DocumentDetailOut)
async def get_document(
    document_id: str,
    user: CurrentUserDep,
    session: SessionDep,
) -> DocumentDetailOut:
    repo = DocumentRepository(session)
    doc, chunks = await repo.get_document_with_chunks(user_id=user.id, document_id=document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return DocumentDetailOut(
        **DocumentOut.model_validate(doc).model_dump(exclude={"chunk_count"}),
        chunk_count=len(chunks),
        raw_text=doc.raw_text,
        chunks=[DocumentChunkOut.model_validate(c) for c in chunks],
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    user: CurrentUserDep,
    session: SessionDep,
) -> None:
    repo = DocumentRepository(session)
    deleted = await repo.delete_document(user_id=user.id, document_id=document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found.")
