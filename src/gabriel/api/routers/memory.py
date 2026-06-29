from __future__ import annotations

from fastapi import APIRouter, Depends

from gabriel.api.dependencies import GatewayService, build_command, get_execution_context, get_gateway_service
from gabriel.api.schema import MemoryCreateRequest, MemoryDeleteResponse, MemoryListResponse
from gabriel.runtime.context import ExecutionContext

router = APIRouter(prefix="/memory", tags=["Memory"])


@router.get("", response_model=MemoryListResponse)
async def get_memory(
    context: ExecutionContext = Depends(get_execution_context),
    service: GatewayService = Depends(get_gateway_service),
) -> MemoryListResponse:
    return MemoryListResponse(items=service.list_memory(context.organization))


@router.post("", response_model=dict, status_code=201)
async def create_memory(
    payload: MemoryCreateRequest,
    context: ExecutionContext = Depends(get_execution_context),
    service: GatewayService = Depends(get_gateway_service),
) -> dict:
    entry = service.create_memory_entry(
        organization_id=context.organization,
        content=payload.content,
        metadata=payload.metadata,
    )
    command = build_command(
        context,
        "write_memory",
        {"memory_id": entry["id"], "content": payload.content, "metadata": payload.metadata},
        action_name="memory:write",
    )
    await service.dispatch_command(command, context)
    return entry


@router.delete("/{memory_id}", response_model=MemoryDeleteResponse)
async def delete_memory(
    memory_id: str,
    context: ExecutionContext = Depends(get_execution_context),
    service: GatewayService = Depends(get_gateway_service),
) -> MemoryDeleteResponse:
    deleted = service.delete_memory_entry(memory_id)
    command = build_command(
        context,
        "delete_memory",
        {"memory_id": memory_id},
        action_name="memory:delete",
    )
    await service.dispatch_command(command, context)
    return MemoryDeleteResponse(deleted=deleted, id=memory_id)
