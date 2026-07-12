"""Notification endpoints (recipient-scoped, DB-backed).

    GET   /notifications                  — paginated listing (?unread_only=&limit=&offset=)
    POST  /notifications/read-all         — mark all of the caller's notifications read
    POST  /notifications/{grn}/read       — mark a single notification read
    PATCH /notifications/{grn}            — legacy alias for marking read

The caller's recipient identity resolves to their User GRN when a user record
exists for the authenticated principal, falling back to the principal id
(service accounts / API keys). Capability enforcement comes from
``notification:*`` actions in ``gabriel.policy.capabilities``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gabriel.api.dependencies import get_db_session_factory, get_execution_context
from gabriel.api.errors import GabrielAPIError
from gabriel.notification.service import NotificationService
from gabriel.resource.exceptions import ResourceNotFoundError
from gabriel.resource.grn import GRN
from gabriel.runtime.context import ExecutionContext
from gabriel.user.service import UserService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


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


async def _resolve_recipient(session: AsyncSession, context: ExecutionContext) -> str:
    """The caller's recipient identity: user GRN when known, else principal id."""
    user = await UserService(session).get_user_by_principal(str(context.principal.id))
    return str(user.grn) if user is not None else str(context.principal.id)


@router.get("")
async def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    async with session_factory() as session:
        recipient = await _resolve_recipient(session, context)
        service = NotificationService(session)
        items, total = await service.list_notifications(
            context.organization,
            recipient,
            unread_only=unread_only,
            limit=limit,
            offset=offset,
        )
        unread = await service.unread_count(context.organization, recipient)
        return {
            "items": [item.public_view() for item in items],
            "total": total,
            "unread_count": unread,
            "limit": limit,
            "offset": offset,
        }


@router.post("/read-all")
async def mark_all_read(
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    async with session_factory() as session:
        recipient = await _resolve_recipient(session, context)
        count = await NotificationService(session).mark_all_read(
            context.organization,
            recipient,
            read_by=str(context.principal.id),
            correlation_id=str(context.correlation_id),
        )
        return {"ok": True, "marked_read": count}


async def _mark_one_read(
    grn: str,
    context: ExecutionContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> dict:
    _require_same_org(context, grn)
    async with session_factory() as session:
        recipient = await _resolve_recipient(session, context)
        try:
            notification = await NotificationService(session).mark_read(
                grn,
                org_id=context.organization,
                recipient=recipient,
                read_by=str(context.principal.id),
                correlation_id=str(context.correlation_id),
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return notification.public_view()


@router.post("/{grn:path}/read")
async def mark_read(
    grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    return await _mark_one_read(grn, context, session_factory)


@router.patch("/{grn:path}")
async def mark_read_legacy(
    grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    """Legacy alias kept for backwards compatibility with earlier clients."""
    return await _mark_one_read(grn, context, session_factory)
