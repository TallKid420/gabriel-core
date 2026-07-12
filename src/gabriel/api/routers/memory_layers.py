"""Memory layer endpoints (org-scoped, DB-backed).

    GET    /memory/layers          — paginated listing (?scope=&subject_grn=&tag=)
    POST   /memory/layers          — create an entry
    GET    /memory/layers/{grn}    — fetch an entry
    PATCH  /memory/layers/{grn}    — update value/tags/expiry
    DELETE /memory/layers/{grn}    — hard delete (audit event preserved)

Governed memory *metadata* entries (Universal Resources with GRNs, backed by
the ``memory_layer_entries`` table) — distinct from the runtime MGE working
memory in ``memory_entries``. This router MUST be registered before the
legacy ``/memory`` gateway router so its more specific prefix wins.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gabriel.api.dependencies import get_db_session_factory, get_execution_context
from gabriel.api.errors import GabrielAPIError
from gabriel.memory.layer_models import MemoryScope
from gabriel.memory.layer_service import MemoryLayerService
from gabriel.resource.exceptions import DuplicateResourceError, ResourceNotFoundError
from gabriel.resource.grn import GRN
from gabriel.runtime.context import ExecutionContext

router = APIRouter(prefix="/memory/layers", tags=["Memory Layers"])


class MemoryLayerCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=255)
    value: Any
    scope: str = MemoryScope.ORG.value
    subject_grn: str | None = None
    tags: list[str] | None = None
    expires_at: datetime | None = None
    metadata: dict[str, Any] | None = None


class MemoryLayerUpdateRequest(BaseModel):
    value: Any | None = None
    tags: list[str] | None = None
    expires_at: datetime | None = None
    clear_expiry: bool = False
    metadata: dict[str, Any] | None = None


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


def _parse_scope(value: str | None) -> MemoryScope | None:
    if value is None:
        return None
    try:
        return MemoryScope(value)
    except ValueError as exc:
        raise GabrielAPIError(f"Unknown memory scope '{value}'", status_code=422) from exc


@router.get("")
async def list_entries(
    scope: str | None = Query(default=None),
    subject_grn: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    parsed_scope = _parse_scope(scope)
    async with session_factory() as session:
        items, total = await MemoryLayerService(session).list_entries(
            context.organization,
            scope=parsed_scope,
            subject_grn=subject_grn,
            tag=tag,
            limit=limit,
            offset=offset,
        )
        return {
            "items": [item.public_view() for item in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.post("", status_code=201)
async def create_entry(
    body: MemoryLayerCreateRequest,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    parsed_scope = _parse_scope(body.scope)
    async with session_factory() as session:
        try:
            entry = await MemoryLayerService(session).create_entry(
                context.organization,
                body.key,
                body.value,
                created_by=str(context.principal.id),
                scope=parsed_scope or MemoryScope.ORG,
                subject_grn=body.subject_grn,
                tags=body.tags,
                expires_at=body.expires_at,
                metadata=body.metadata,
                correlation_id=str(context.correlation_id),
            )
        except DuplicateResourceError as exc:
            raise GabrielAPIError(str(exc), status_code=409) from exc
        return entry.public_view()


@router.get("/{grn:path}")
async def get_entry(
    grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    _require_same_org(context, grn)
    async with session_factory() as session:
        try:
            entry = await MemoryLayerService(session).get_entry(
                grn, org_id=context.organization
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return entry.public_view()


@router.patch("/{grn:path}")
async def update_entry(
    grn: str,
    body: MemoryLayerUpdateRequest,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    _require_same_org(context, grn)
    async with session_factory() as session:
        try:
            entry = await MemoryLayerService(session).update_entry(
                grn,
                updated_by=str(context.principal.id),
                org_id=context.organization,
                value=body.value,
                tags=body.tags,
                expires_at=body.expires_at,
                clear_expiry=body.clear_expiry,
                metadata=body.metadata,
                correlation_id=str(context.correlation_id),
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return entry.public_view()


@router.delete("/{grn:path}", status_code=204)
async def delete_entry(
    grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    _require_same_org(context, grn)
    async with session_factory() as session:
        try:
            await MemoryLayerService(session).delete_entry(
                grn,
                deleted_by=str(context.principal.id),
                org_id=context.organization,
                correlation_id=str(context.correlation_id),
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
    return None
