"""Conversation endpoints (org-scoped, DB-backed).

    GET    /conversations                     — paginated listing (?status=&limit=&offset=)
    POST   /conversations                     — create a conversation
    GET    /conversations/{grn}/messages      — paginated message listing
    POST   /conversations/{grn}/messages      — append a message
    GET    /conversations/{grn}               — fetch a conversation
    PATCH  /conversations/{grn}               — update title/status/participants/agent
    DELETE /conversations/{grn}               — soft-delete (audit trail preserved)

All routes operate strictly within the authenticated organization (tenant
isolation on top of PEEL middleware; capability enforcement comes from
``conversation:*`` / ``message:*`` actions in ``gabriel.policy.capabilities``).

NOTE: the ``/messages`` routes are declared *before* the bare ``/{grn:path}``
routes — the greedy ``:path`` converter would otherwise swallow them.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gabriel.api.dependencies import get_db_session_factory, get_execution_context
from gabriel.api.errors import GabrielAPIError
from gabriel.api.tenancy import require_same_org
from gabriel.conversation.message_models import MessageRole
from gabriel.conversation.message_service import ConversationClosedError, MessageService
from gabriel.conversation.models import ConversationStatus
from gabriel.conversation.service import ConversationService
from gabriel.resource.exceptions import ResourceNotFoundError
from gabriel.resource.grn import GRN
from gabriel.runtime.context import ExecutionContext

router = APIRouter(prefix="/conversations", tags=["Conversations"])


class ConversationCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    participants: list[str] | None = None
    agent_grn: str | None = None
    metadata: dict[str, Any] | None = None
    labels: dict[str, str] | None = None


class ConversationUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    status: str | None = None
    participants: list[str] | None = None
    agent_grn: str | None = None
    metadata: dict[str, Any] | None = None


class MessageCreateRequest(BaseModel):
    role: str
    content: str
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    model: str | None = None
    metadata: dict[str, Any] | None = None


def _parse_status(value: str | None) -> ConversationStatus | None:
    if value is None:
        return None
    try:
        return ConversationStatus(value)
    except ValueError as exc:
        raise GabrielAPIError(
            f"Unknown conversation status '{value}'", status_code=422
        ) from exc


@router.get("")
async def list_conversations(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    parsed_status = _parse_status(status)
    async with session_factory() as session:
        items, total = await ConversationService(session).list_conversations(
            context.organization, status=parsed_status, limit=limit, offset=offset
        )
        return {
            "items": [item.public_view() for item in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.post("", status_code=201)
async def create_conversation(
    body: ConversationCreateRequest,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    async with session_factory() as session:
        conversation = await ConversationService(session).create_conversation(
            context.organization,
            body.title,
            created_by=str(context.principal.id),
            participants=body.participants,
            agent_grn=body.agent_grn,
            metadata=body.metadata,
            labels=body.labels,
            correlation_id=str(context.correlation_id),
        )
        return conversation.public_view()


# ── Messages (declared before the greedy /{grn:path} routes) ────────────────


@router.get("/{grn:path}/messages")
async def list_messages(
    grn: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    require_same_org(context, grn)
    async with session_factory() as session:
        service = MessageService(session)
        try:
            # Ensure the conversation exists in this org before listing.
            await service.conversations.get_by_grn(grn, org_id=context.organization)
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        items, total = await service.list_messages(
            grn, org_id=context.organization, limit=limit, offset=offset
        )
        return {
            "items": [item.public_view() for item in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.post("/{grn:path}/messages", status_code=201)
async def create_message(
    grn: str,
    body: MessageCreateRequest,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    require_same_org(context, grn)
    try:
        role = MessageRole(body.role)
    except ValueError as exc:
        raise GabrielAPIError(f"Unknown message role '{body.role}'", status_code=422) from exc

    async with session_factory() as session:
        try:
            message = await MessageService(session).create_message(
                grn,
                org_id=context.organization,
                created_by=str(context.principal.id),
                role=role,
                content=body.content,
                prompt_tokens=body.prompt_tokens,
                completion_tokens=body.completion_tokens,
                total_tokens=body.total_tokens,
                model=body.model,
                metadata=body.metadata,
                correlation_id=str(context.correlation_id),
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        except ConversationClosedError as exc:
            raise GabrielAPIError(str(exc), status_code=409) from exc
        return message.public_view()


# ── Conversation item routes ─────────────────────────────────────────────────


@router.get("/{grn:path}")
async def get_conversation(
    grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    require_same_org(context, grn)
    async with session_factory() as session:
        try:
            conversation = await ConversationService(session).get_conversation(
                grn, org_id=context.organization
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return conversation.public_view()


@router.patch("/{grn:path}")
async def update_conversation(
    grn: str,
    body: ConversationUpdateRequest,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    require_same_org(context, grn)
    parsed_status = _parse_status(body.status)
    async with session_factory() as session:
        try:
            conversation = await ConversationService(session).update_conversation(
                grn,
                updated_by=str(context.principal.id),
                org_id=context.organization,
                title=body.title,
                status=parsed_status,
                participants=body.participants,
                agent_grn=body.agent_grn,
                metadata=body.metadata,
                correlation_id=str(context.correlation_id),
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return conversation.public_view()


@router.delete("/{grn:path}")
async def delete_conversation(
    grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    require_same_org(context, grn)
    async with session_factory() as session:
        try:
            conversation = await ConversationService(session).delete_conversation(
                grn,
                deleted_by=str(context.principal.id),
                org_id=context.organization,
                correlation_id=str(context.correlation_id),
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return conversation.public_view()
