"""Gateway AI Runtime endpoints (Phase 3).

    POST   /gateway/chat/stream            — SSE streaming chat turn
    POST   /gateway/chat                   — buffered (non-streaming) chat turn
    GET    /gateway/providers              — registered providers + health
    GET    /gateway/providers/{name}/models— models available on a provider
    GET    /gateway/tools                  — runtime tools exposed to the LLM
    GET    /gateway/sessions               — active chat sessions (this org)
    DELETE /gateway/sessions/{session_id}  — end an active session

The Gateway orchestrates LLM calls; durable business data (conversations,
messages, agents) stays with the Phase-2 slices. Capability enforcement:
``gateway:*`` actions in ``gabriel.policy.capabilities``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from gabriel.api.dependencies import (
    get_chat_runtime_service,
    get_execution_context,
    get_provider_registry,
    get_session_manager,
)
from gabriel.api.errors import GabrielAPIError
from gabriel.gateway.providers.base import (
    ProviderConnectionError,
    ProviderError,
    ProviderNotFoundError,
)
from gabriel.gateway.providers.registry import ProviderRegistry
from gabriel.gateway.service import ChatRuntimeError, ChatRuntimeService
from gabriel.gateway.sessions import SessionManager
from gabriel.resource.grn import GRN
from gabriel.runtime.context import ExecutionContext

router = APIRouter(prefix="/gateway", tags=["Gateway"])


class ChatTurnRequest(BaseModel):
    conversation_grn: str = Field(min_length=1)
    content: str = Field(min_length=1)
    model: str | None = None
    provider: str | None = None


def _require_same_org(context: ExecutionContext, grn_str: str) -> None:
    try:
        grn = GRN.parse(grn_str)
    except Exception as exc:
        raise GabrielAPIError(f"Invalid GRN '{grn_str}'", status_code=422) from exc
    if grn.org_id != context.organization:
        raise GabrielAPIError("Cross-organization access is forbidden", status_code=403)


@router.post("/chat/stream")
async def stream_chat(
    body: ChatTurnRequest,
    context: ExecutionContext = Depends(get_execution_context),
    runtime: ChatRuntimeService = Depends(get_chat_runtime_service),
) -> StreamingResponse:
    """Stream one chat turn as Server-Sent Events."""
    _require_same_org(context, body.conversation_grn)
    return StreamingResponse(
        runtime.stream_turn(
            org_id=context.organization,
            principal_id=str(context.principal.id),
            conversation_grn=body.conversation_grn,
            content=body.content,
            model_override=body.model,
            provider_override=body.provider,
            correlation_id=str(context.correlation_id),
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat")
async def chat(
    body: ChatTurnRequest,
    context: ExecutionContext = Depends(get_execution_context),
    runtime: ChatRuntimeService = Depends(get_chat_runtime_service),
):
    """Run one chat turn and return the buffered result."""
    _require_same_org(context, body.conversation_grn)
    try:
        return await runtime.complete_turn(
            org_id=context.organization,
            principal_id=str(context.principal.id),
            conversation_grn=body.conversation_grn,
            content=body.content,
            model_override=body.model,
            provider_override=body.provider,
            correlation_id=str(context.correlation_id),
        )
    except ChatRuntimeError as exc:
        status = 502 if "reach" in str(exc).lower() else 422
        raise GabrielAPIError(str(exc), status_code=status) from exc


@router.get("/providers")
async def list_providers(
    context: ExecutionContext = Depends(get_execution_context),
    providers: ProviderRegistry = Depends(get_provider_registry),
):
    items = []
    for name in providers.list_providers():
        health = await providers.get(name).health_check()
        items.append(
            {
                "name": name,
                "default": name == providers.default_provider,
                "healthy": health.healthy,
                "detail": health.detail,
            }
        )
    return {"items": items, "default_provider": providers.default_provider}


@router.get("/providers/{name}/models")
async def list_provider_models(
    name: str,
    context: ExecutionContext = Depends(get_execution_context),
    providers: ProviderRegistry = Depends(get_provider_registry),
):
    try:
        provider = providers.get(name)
        models = await provider.list_models()
    except ProviderNotFoundError as exc:
        raise GabrielAPIError(str(exc), status_code=404) from exc
    except ProviderConnectionError as exc:
        raise GabrielAPIError(str(exc), status_code=502) from exc
    except ProviderError as exc:
        raise GabrielAPIError(str(exc), status_code=502) from exc
    return {
        "items": [
            {"name": m.name, "provider": m.provider, "metadata": m.metadata}
            for m in models
        ]
    }


@router.get("/tools")
async def list_runtime_tools(
    context: ExecutionContext = Depends(get_execution_context),
    runtime: ChatRuntimeService = Depends(get_chat_runtime_service),
):
    return {"items": runtime.tools.llm_specs()}


@router.get("/sessions")
async def list_sessions(
    context: ExecutionContext = Depends(get_execution_context),
    sessions: SessionManager = Depends(get_session_manager),
):
    items = [s.public_view() for s in sessions.list_active(context.organization)]
    return {"items": items, "total": len(items)}


@router.delete("/sessions/{session_id}")
async def end_session(
    session_id: str,
    context: ExecutionContext = Depends(get_execution_context),
    sessions: SessionManager = Depends(get_session_manager),
):
    session = sessions.get(session_id)
    if session is None or session.org_id != context.organization:
        raise GabrielAPIError(f"Session {session_id} not found", status_code=404)
    sessions.end(session_id)
    return {"session_id": session_id, "ended": True}
