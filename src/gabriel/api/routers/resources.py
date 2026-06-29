from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from gabriel.api.dependencies import GatewayService, build_command, get_execution_context, get_gateway_service
from gabriel.api.schema import (
    ResourceCreateRequest,
    ResourceDeleteResponse,
    ResourceResponse,
    ResourceUpdateRequest,
)
from gabriel.runtime.context import ExecutionContext

router = APIRouter(prefix="/resources", tags=["Resources"])


@router.get("/{grn:path}", response_model=ResourceResponse)
async def get_resource(
    grn: str,
    service: GatewayService = Depends(get_gateway_service),
) -> ResourceResponse:
    resource = service.get_resource(grn)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    return ResourceResponse(
        grn=resource["grn"],
        resource_type=resource.get("resource_type"),
        state=resource.get("state"),
        attributes=resource.get("attributes", {}),
    )


@router.post("", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_resource(
    payload: ResourceCreateRequest,
    context: ExecutionContext = Depends(get_execution_context),
    service: GatewayService = Depends(get_gateway_service),
) -> ResourceResponse:
    command = build_command(
        context,
        "create_resource",
        {
            "resource_type": payload.resource_type,
            "resource_id": payload.resource_id,
            "version": payload.version,
            "attributes": payload.attributes,
        },
        action_name="resource:create",
    )
    events = await service.dispatch_command(command, context)
    event = events[0]
    return ResourceResponse(
        grn=event.payload["grn"],
        resource_type=payload.resource_type,
        state="active",
        attributes=payload.attributes,
    )


@router.patch("/{grn:path}", response_model=ResourceResponse)
async def update_resource(
    grn: str,
    payload: ResourceUpdateRequest,
    context: ExecutionContext = Depends(get_execution_context),
    service: GatewayService = Depends(get_gateway_service),
) -> ResourceResponse:
    command = build_command(
        context,
        "update_resource",
        {"attributes": payload.attributes, "grn": grn},
        action_name="resource:update",
        target_resource_grn=grn,
    )
    await service.dispatch_command(command, context)
    resource = service.get_resource(grn)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    return ResourceResponse(
        grn=resource["grn"],
        resource_type=resource.get("resource_type"),
        state=resource.get("state"),
        attributes=resource.get("attributes", {}),
    )


@router.delete("/{grn:path}", response_model=ResourceDeleteResponse)
async def delete_resource(
    grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    service: GatewayService = Depends(get_gateway_service),
) -> ResourceDeleteResponse:
    command = build_command(
        context,
        "delete_resource",
        {"grn": grn},
        action_name="resource:delete",
        target_resource_grn=grn,
    )
    await service.dispatch_command(command, context)
    return ResourceDeleteResponse(deleted=True, grn=grn)
