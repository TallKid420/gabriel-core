from __future__ import annotations

from fastapi import APIRouter, Depends, status

from gabriel.runtime.context import ExecutionContext
from gabriel.api.services.notification import NotificationService
from gabriel.api.dependencies import (
    get_notification_service, 
    get_execution_context
)
from gabriel.api.schema import (
    OkResponse, 
    Notification
)

router = APIRouter(prefix="/notifications", tags=["notifications"])

@router.get("", response_model=list[Notification], status_code=status.HTTP_200_OK)
async def get_notifications(
    context: ExecutionContext = Depends(get_execution_context),
    service: NotificationService = Depends(get_notification_service),
):
    # Placeholder implementation for fetching notifications
    return service.get_notifications(context.principal)

@router.post("", response_model=OkResponse, status_code=status.HTTP_200_OK)
async def mark_all_read(
    context: ExecutionContext = Depends(get_execution_context),
    service: NotificationService = Depends(get_notification_service),
) -> OkResponse:
    # Placeholder implementation for marking all notifications as read
    service.mark_all_read(context.principal)
    return OkResponse(ok=True, detail="All notifications marked as read.")

@router.patch("/{notification_grn:path}", response_model=OkResponse, status_code=status.HTTP_200_OK)
async def change_read_status(
    notification_grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    service: NotificationService = Depends(get_notification_service),
) -> OkResponse:
    service.change_read_status(context.principal, notification_grn)
    return OkResponse(ok=True, detail=f"Notification {notification_grn} marked as read.")