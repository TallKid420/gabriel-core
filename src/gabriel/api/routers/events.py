from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from gabriel.runtime.context import ExecutionContext
from gabriel.api.schema import EventListResponse, EventResponse
from gabriel.api.dependencies import (
    GatewayService, 
    get_gateway_service, 
    get_current_context, 
)

router = APIRouter(prefix="/events", tags=["Events"])


@router.get("", response_model=EventListResponse)
async def get_events(service: GatewayService = Depends(get_gateway_service)) -> EventListResponse:
    events = [EventResponse(**event.model_dump(mode="json")) for event in service.list_events()]
    return EventListResponse(items=events)


@router.get("/stream")
async def stream_events(
    context: ExecutionContext = Depends(get_current_context),
) -> None:
    raise HTTPException(status_code=501, detail="Event streaming is not implemented yet")


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(event_id: str, service: GatewayService = Depends(get_gateway_service)) -> EventResponse:
    event = service.get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return EventResponse(**event.model_dump(mode="json"))
