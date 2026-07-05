from __future__ import annotations

from fastapi import APIRouter, Depends, status

from gabriel.runtime.context import ExecutionContext
from gabriel.api.services.chat import ChatService
from gabriel.api.dependencies import (
    get_gateway_service,
    get_execution_context, 
    get_chat_service, 
    build_command, 
    GatewayService
)
from gabriel.api.schema import (
    ChatSummaryResponse, 
    ChatCreateRequest, 
    ResourceResponse
)

router = APIRouter(prefix="/chat", tags=["chat"])

@router.get("/conversations", response_model=list[ChatSummaryResponse])
async def list_conversations(
    context: ExecutionContext = Depends(get_execution_context),
    service: ChatService = Depends(get_chat_service)
):
    chatConversations = service.get_chat_summary(context.principal)
    return [
        ChatSummaryResponse(
            id=completion.id,
            title=completion.title,
            agentGRN=completion.agentGRN,
            messageCount=completion.messageCount,
            lastMessagePreview=completion.lastMessagePreview,
            createdAt=completion.createdAt,
            updatedAt=completion.updatedAt,
        )
        for completion in chatConversations
    ]

@router.post("/conversations", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(
    payload: ChatCreateRequest,
    context: ExecutionContext = Depends(get_execution_context),
    service: GatewayService = Depends(get_gateway_service),
) -> ResourceResponse:
    command = build_command(
        context,
        "new_chat",
        {
            "resource_type": "chat",
            "attributes": {
                "title": payload.title,
                "agentGRN": payload.agentGRN,
                "metadata": payload.metadata,
            },
        },
        action_name="chat:create",
    )
    events = await service.dispatch_command(command, context)
    created = events[0]
    return ResourceResponse(
        grn=created.payload["grn"],
        resource_type="chat",
        state="active",
        attributes=created.payload.get("attributes", {}),
    )