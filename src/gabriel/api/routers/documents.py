"""Documents router (org-scoped, DB-backed — Phase 4).

    POST   /documents                  — upload (multipart) + optional processing
    GET    /documents                  — paginated listing (?status=&knowledge_source_grn=)
    GET    /documents/{grn}            — fetch document metadata
    GET    /documents/{grn}/content    — normalized text content
    GET    /documents/{grn}/chunks     — paginated chunk listing
    POST   /documents/{grn}/process    — (re-)chunk & embed
    DELETE /documents/{grn}            — soft delete (purges chunks)

Documents are Universal Resources (GRN-addressed rows in the ``documents``
table); file content lives on the local filesystem via the DiskContentStore
(``GABRIEL_CONTENT_ROOT``). Uploads default to immediate processing
(chunking + embedding); embedding failures degrade gracefully so uploads
succeed even when no embedding provider is reachable.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gabriel.api.dependencies import get_db_session_factory, get_execution_context
from gabriel.api.errors import GabrielAPIError
from gabriel.document.library import (
    DocumentLibraryService,
    UnsupportedDocumentTypeError,
)
from gabriel.document.models import DocumentStatus
from gabriel.document.normalizer import NormalizationError
from gabriel.document.processing import DocumentProcessingService
from gabriel.knowledge.vector_store import ChunkVectorStore
from gabriel.resource.exceptions import ResourceNotFoundError
from gabriel.resource.grn import GRN
from gabriel.runtime.context import ExecutionContext

router = APIRouter(prefix="/documents", tags=["Documents"])


def _require_same_org(context: ExecutionContext, grn_str: str) -> None:
    """Reject GRNs that address a different tenant."""
    try:
        grn = GRN.parse(grn_str)
    except Exception as exc:
        raise GabrielAPIError(f"Invalid GRN '{grn_str}'", status_code=422) from exc
    if grn.org_id != context.organization:
        raise GabrielAPIError(
            "Cross-organization access is forbidden", status_code=403
        )


def _parse_status(value: str | None) -> DocumentStatus | None:
    if value is None:
        return None
    try:
        return DocumentStatus(value)
    except ValueError as exc:
        raise GabrielAPIError(
            f"Unknown document status '{value}'", status_code=422
        ) from exc


def _resolve_embedder(request: Request):
    """Best-effort embedding provider from app state (None when unwired)."""
    registry = getattr(request.app.state, "embedding_registry", None)
    if registry is None:
        return None
    try:
        return registry.resolve()
    except Exception:  # noqa: BLE001 - empty registry → degrade to no vectors
        return None


@router.post("", status_code=201)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    source_uri: str | None = Form(default=None),
    knowledge_source_grn: str | None = Form(default=None),
    process: bool = Form(default=True),
    chunk_size: int | None = Form(default=None),
    chunk_overlap: int | None = Form(default=None),
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    """Upload a document (PDF/TXT/MD/DOCX) and optionally process it."""
    content = await file.read()
    async with session_factory() as session:
        library = DocumentLibraryService(session)
        try:
            document = await library.upload_document(
                context.organization,
                filename=file.filename or "upload",
                content=content,
                created_by=str(context.principal.id),
                media_type=file.content_type,
                source_uri=source_uri,
                knowledge_source_grn=knowledge_source_grn,
                correlation_id=str(context.correlation_id),
                commit=True,
            )
        except UnsupportedDocumentTypeError as exc:
            raise GabrielAPIError(str(exc), status_code=422) from exc
        except NormalizationError as exc:
            raise GabrielAPIError(str(exc), status_code=422) from exc

        if process:
            processor = DocumentProcessingService(
                session, library=library, embedder=_resolve_embedder(request)
            )
            result = await processor.process_document(
                str(document.grn),
                org_id=context.organization,
                processed_by=str(context.principal.id),
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                correlation_id=str(context.correlation_id),
            )
            document = result.document

        return document.public_view()


@router.get("")
async def list_documents(
    status: str | None = Query(default=None),
    knowledge_source_grn: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    parsed_status = _parse_status(status)
    async with session_factory() as session:
        items, total = await DocumentLibraryService(session).list_documents(
            context.organization,
            status=parsed_status,
            knowledge_source_grn=knowledge_source_grn,
            limit=limit,
            offset=offset,
        )
        return {
            "items": [item.public_view() for item in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.get("/{grn:path}/content")
async def get_document_content(
    grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    _require_same_org(context, grn)
    async with session_factory() as session:
        library = DocumentLibraryService(session)
        try:
            document = await library.get_document(grn, org_id=context.organization)
            text = await library.get_document_text(grn, org_id=context.organization)
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return {
            "grn": str(document.grn),
            "filename": document.filename,
            "media_type": document.media_type,
            "content": text,
        }


@router.get("/{grn:path}/chunks")
async def list_document_chunks(
    grn: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    _require_same_org(context, grn)
    async with session_factory() as session:
        try:
            await DocumentLibraryService(session).get_document(
                grn, org_id=context.organization
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        chunks, total = await ChunkVectorStore(session).list_for_document(
            grn, context.organization, limit=limit, offset=offset
        )
        return {
            "items": [
                {
                    "chunk_id": chunk.id,
                    "document_grn": chunk.document_grn,
                    "knowledge_source_grn": chunk.knowledge_source_grn,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "token_count": chunk.token_count,
                    "embedded": chunk.embedding is not None,
                    "embedding_model": chunk.embedding_model,
                    "metadata": chunk.chunk_metadata or {},
                }
                for chunk in chunks
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.post("/{grn:path}/process")
async def process_document(
    grn: str,
    request: Request,
    chunk_size: int | None = Query(default=None, ge=1),
    chunk_overlap: int | None = Query(default=None, ge=0),
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    """(Re-)chunk and embed a document's text."""
    _require_same_org(context, grn)
    async with session_factory() as session:
        processor = DocumentProcessingService(
            session, embedder=_resolve_embedder(request)
        )
        try:
            result = await processor.process_document(
                grn,
                org_id=context.organization,
                processed_by=str(context.principal.id),
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                correlation_id=str(context.correlation_id),
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return {
            "document": result.document.public_view(),
            "chunk_count": result.chunk_count,
            "embedded": result.embedded,
            "embedding_model": result.embedding_model,
        }


@router.get("/{grn:path}")
async def get_document(
    grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    _require_same_org(context, grn)
    async with session_factory() as session:
        try:
            document = await DocumentLibraryService(session).get_document(
                grn, org_id=context.organization
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return document.public_view()


@router.delete("/{grn:path}", status_code=204)
async def delete_document(
    grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    """Soft-delete a document; its derived chunks are purged."""
    _require_same_org(context, grn)
    async with session_factory() as session:
        try:
            await DocumentLibraryService(session).delete_document(
                grn,
                deleted_by=str(context.principal.id),
                org_id=context.organization,
                correlation_id=str(context.correlation_id),
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
    return None
