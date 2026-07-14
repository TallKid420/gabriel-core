"""Knowledge router (org-scoped, DB-backed — Phase 4).

    POST   /knowledge/sources                       — create a knowledge source
    GET    /knowledge/sources                       — paginated listing (?status=)
    GET    /knowledge/sources/{grn}                 — fetch a source
    PATCH  /knowledge/sources/{grn}                 — update name/description/status
    DELETE /knowledge/sources/{grn}                 — soft delete (detaches documents)
    GET    /knowledge/sources/{grn}/documents       — list attached documents
    POST   /knowledge/sources/{grn}/documents       — attach a document
    POST   /knowledge/sources/{grn}/documents/detach — detach a document
    POST   /knowledge/search                        — similarity search over chunks

Knowledge sources are Universal Resources that group documents into
retrievable collections; agents reference them by GRN and the gateway
retrieves relevant chunks automatically during chat turns (RAG).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gabriel.api.dependencies import get_db_session_factory, get_execution_context
from gabriel.api.errors import GabrielAPIError
from gabriel.knowledge.retrieval import KnowledgeRetriever
from gabriel.knowledge.source_models import KnowledgeSourceStatus
from gabriel.knowledge.source_service import KnowledgeSourceService
from gabriel.resource.exceptions import ResourceNotFoundError
from gabriel.resource.grn import GRN
from gabriel.runtime.context import ExecutionContext

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


class KnowledgeSourceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    description: str = ""
    metadata: dict | None = None
    labels: dict[str, str] | None = None


class KnowledgeSourceUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    metadata: dict | None = None


class AttachDocumentRequest(BaseModel):
    document_grn: str = Field(min_length=1)


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    knowledge_source_grns: list[str] | None = None
    document_grns: list[str] | None = None
    limit: int = Field(default=5, ge=1, le=50)


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


def _parse_status(value: str | None) -> KnowledgeSourceStatus | None:
    if value is None:
        return None
    try:
        return KnowledgeSourceStatus(value)
    except ValueError as exc:
        raise GabrielAPIError(
            f"Unknown knowledge source status '{value}'", status_code=422
        ) from exc


# ----------------------------------------------------------------- search


@router.post("/search")
async def search_knowledge(
    body: KnowledgeSearchRequest,
    request: Request,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    """Similarity search over document chunks (keyword fallback)."""
    for grn in (body.knowledge_source_grns or []) + (body.document_grns or []):
        _require_same_org(context, grn)
    retriever = getattr(request.app.state, "knowledge_retriever", None)
    if retriever is None:
        retriever = KnowledgeRetriever(session_factory)
    results = await retriever.search_chunks(
        org_id=context.organization,
        query=body.query,
        knowledge_source_grns=body.knowledge_source_grns,
        document_grns=body.document_grns,
        limit=body.limit,
    )
    return {
        "query": body.query,
        "items": [result.public_view() for result in results],
        "total": len(results),
    }


# ---------------------------------------------------------------- sources


@router.post("/sources", status_code=201)
async def create_source(
    body: KnowledgeSourceCreateRequest,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    async with session_factory() as session:
        source = await KnowledgeSourceService(session).create_source(
            context.organization,
            body.name,
            created_by=str(context.principal.id),
            description=body.description,
            metadata=body.metadata,
            labels=body.labels,
            correlation_id=str(context.correlation_id),
        )
        return source.public_view()


@router.get("/sources")
async def list_sources(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    parsed_status = _parse_status(status)
    async with session_factory() as session:
        items, total = await KnowledgeSourceService(session).list_sources(
            context.organization, status=parsed_status, limit=limit, offset=offset
        )
        return {
            "items": [item.public_view() for item in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.get("/sources/{grn:path}/documents")
async def list_source_documents(
    grn: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    _require_same_org(context, grn)
    async with session_factory() as session:
        try:
            items, total = await KnowledgeSourceService(session).list_documents(
                grn, org_id=context.organization, limit=limit, offset=offset
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return {
            "items": [item.public_view() for item in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.post("/sources/{grn:path}/documents/detach")
async def detach_document(
    grn: str,
    body: AttachDocumentRequest,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    _require_same_org(context, grn)
    _require_same_org(context, body.document_grn)
    async with session_factory() as session:
        try:
            document = await KnowledgeSourceService(session).detach_document(
                grn,
                body.document_grn,
                org_id=context.organization,
                updated_by=str(context.principal.id),
                correlation_id=str(context.correlation_id),
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return document.public_view()


@router.post("/sources/{grn:path}/documents", status_code=201)
async def attach_document(
    grn: str,
    body: AttachDocumentRequest,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    _require_same_org(context, grn)
    _require_same_org(context, body.document_grn)
    async with session_factory() as session:
        try:
            document = await KnowledgeSourceService(session).attach_document(
                grn,
                body.document_grn,
                org_id=context.organization,
                updated_by=str(context.principal.id),
                correlation_id=str(context.correlation_id),
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return document.public_view()


@router.get("/sources/{grn:path}")
async def get_source(
    grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    _require_same_org(context, grn)
    async with session_factory() as session:
        try:
            source = await KnowledgeSourceService(session).get_source(
                grn, org_id=context.organization
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return source.public_view()


@router.patch("/sources/{grn:path}")
async def update_source(
    grn: str,
    body: KnowledgeSourceUpdateRequest,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    _require_same_org(context, grn)
    if body.status is not None:
        _parse_status(body.status)
    async with session_factory() as session:
        try:
            source = await KnowledgeSourceService(session).update_source(
                grn,
                updated_by=str(context.principal.id),
                org_id=context.organization,
                name=body.name,
                description=body.description,
                status=body.status,
                metadata=body.metadata,
                correlation_id=str(context.correlation_id),
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return source.public_view()


@router.delete("/sources/{grn:path}", status_code=204)
async def delete_source(
    grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    _require_same_org(context, grn)
    async with session_factory() as session:
        try:
            await KnowledgeSourceService(session).delete_source(
                grn,
                deleted_by=str(context.principal.id),
                org_id=context.organization,
                correlation_id=str(context.correlation_id),
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
    return None
