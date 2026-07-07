from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from gabriel.runtime.context import ExecutionContext
from gabriel.api.schema import EventListResponse, EventResponse
from gabriel.api.dependencies import (
    GatewayService, 
    EventStreamer,
    get_gateway_service, 
    get_current_context, 
    get_event_streamer,
)

router = APIRouter(prefix="/events", tags=["Events"])


@router.get("", response_model=EventListResponse)
async def get_events(service: GatewayService = Depends(get_gateway_service)) -> EventListResponse:
    events = [EventResponse(**event.model_dump(mode="json")) for event in service.list_events()]
    return EventListResponse(items=events)


@router.get("/stream")
async def stream_events(
    context: ExecutionContext = Depends(get_current_context),
    streamer: EventStreamer = Depends(get_event_streamer),
) -> StreamingResponse:
    return StreamingResponse(
        streamer.stream_events(context.organization),
        media_type="text/event-stream",
    )


@router.get("/audit", response_model=EventListResponse)
async def query_audit_log(
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    principal_id: str | None = Query(default=None),
    decision: str | None = Query(default=None, pattern="^(allow|deny)$"),
    limit: int = Query(default=200, ge=1, le=1000),
    context: ExecutionContext = Depends(get_current_context),
    service: GatewayService = Depends(get_gateway_service),
) -> EventListResponse:
    events = await service.query_audit_log(
        start_time=start_time,
        end_time=end_time,
        principal_id=principal_id,
        decision=decision,
        organization_id=context.organization,
        limit=limit,
    )
    items = [EventResponse(**event.model_dump(mode="json")) for event in events]
    return EventListResponse(items=items)


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(event_id: str, service: GatewayService = Depends(get_gateway_service)) -> EventResponse:
    event = service.get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return EventResponse(**event.model_dump(mode="json"))
