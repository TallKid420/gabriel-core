"""Agent management endpoints (org-scoped, DB-backed).

    GET    /agents                  — paginated listing (?limit=&offset=)
    POST   /agents                  — create an agent
    GET    /agents/{grn}            — fetch an agent
    PATCH  /agents/{grn}            — update management fields
    DELETE /agents/{grn}            — delete an agent
    POST   /agents/{grn}/execute    — execute (gateway command, unchanged)
    POST   /agents/{grn}/enable     — enable (gateway command, unchanged)
    POST   /agents/{grn}/disable    — disable (gateway command, unchanged)

CRUD is backed by the persisted Agent resource slice via
:class:`gabriel.agent.management.AgentManagementService` (Phase 2). The
execute/enable/disable actions still flow through the gateway command path.

NOTE: pydantic v2 reserves the ``model_config`` attribute name, so the request
models expose the field through an alias (wire format stays ``model_config``).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gabriel.agent.management import AgentManagementService, AgentStatus, agent_public_view
from gabriel.agent.repository import AgentRepository
from gabriel.api.dependencies import (
    GatewayService,
    build_command,
    get_db_session_factory,
    get_execution_context,
    get_gateway_service,
)
from gabriel.api.errors import GabrielAPIError
from gabriel.api.schema import AgentExecuteRequest, AgentStateResponse
from gabriel.events.repository import EventRepository
from gabriel.resource.exceptions import ResourceNotFoundError
from gabriel.resource.grn import GRN
from gabriel.runtime.context import ExecutionContext

router = APIRouter(prefix="/agents", tags=["Agents"])


class AgentCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    system_prompt: str = ""
    model_settings: dict[str, Any] | None = Field(default=None, alias="model_config")
    allowed_tools: list[str] | None = None
    knowledge_sources: list[str] | None = None
    status: str = AgentStatus.ACTIVE.value
    runtime: str = "default"
    metadata: dict[str, Any] | None = None
    labels: dict[str, str] | None = None


class AgentUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    system_prompt: str | None = None
    model_settings: dict[str, Any] | None = Field(default=None, alias="model_config")
    allowed_tools: list[str] | None = None
    knowledge_sources: list[str] | None = None
    status: str | None = None
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


def _parse_status(value: str | None) -> AgentStatus | None:
    if value is None:
        return None
    try:
        return AgentStatus(value)
    except ValueError as exc:
        raise GabrielAPIError(f"Unknown agent status '{value}'", status_code=422) from exc


def _service(session: AsyncSession) -> AgentManagementService:
    return AgentManagementService(AgentRepository(session), EventRepository(session))


@router.get("")
async def list_agents(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    async with session_factory() as session:
        items, total = await _service(session).list_agents(
            context.organization, limit=limit, offset=offset
        )
        return {
            "items": [agent_public_view(agent) for agent in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.post("", status_code=201)
async def create_agent(
    body: AgentCreateRequest,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    status = _parse_status(body.status) or AgentStatus.ACTIVE
    async with session_factory() as session:
        agent = await _service(session).create_agent(
            context.organization,
            body.name,
            created_by=str(context.principal.id),
            description=body.description,
            system_prompt=body.system_prompt,
            model_config=body.model_settings,
            allowed_tools=body.allowed_tools,
            knowledge_sources=body.knowledge_sources,
            status=status,
            runtime=body.runtime,
            metadata=body.metadata,
            labels=body.labels,
            correlation_id=str(context.correlation_id),
        )
        return agent_public_view(agent)


@router.post("/{grn:path}/execute", response_model=AgentStateResponse)
async def execute_agent(
    grn: str,
    payload: AgentExecuteRequest,
    context: ExecutionContext = Depends(get_execution_context),
    service: GatewayService = Depends(get_gateway_service),
) -> AgentStateResponse:
    command = build_command(
        context,
        "execute_agent",
        {"grn": grn, "input": payload.input},
        action_name="agent:execute",
        target_resource_grn=grn,
    )
    events = await service.dispatch_command(command, context)
    return AgentStateResponse(grn=grn, status="running", last_event=events[0].type)


@router.post("/{grn:path}/disable", response_model=AgentStateResponse)
async def disable_agent(
    grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    service: GatewayService = Depends(get_gateway_service),
) -> AgentStateResponse:
    command = build_command(
        context,
        "disable_agent",
        {"grn": grn, "state": "disabled"},
        action_name="agent:disable",
        target_resource_grn=grn,
    )
    events = await service.dispatch_command(command, context)
    return AgentStateResponse(grn=grn, status="disabled", last_event=events[0].type)


@router.post("/{grn:path}/enable", response_model=AgentStateResponse)
async def enable_agent(
    grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    service: GatewayService = Depends(get_gateway_service),
) -> AgentStateResponse:
    command = build_command(
        context,
        "enable_agent",
        {"grn": grn, "state": "active"},
        action_name="agent:enable",
        target_resource_grn=grn,
    )
    events = await service.dispatch_command(command, context)
    return AgentStateResponse(grn=grn, status="active", last_event=events[0].type)


@router.get("/{grn:path}")
async def get_agent(
    grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    _require_same_org(context, grn)
    async with session_factory() as session:
        try:
            agent = await _service(session).get_agent(grn, org_id=context.organization)
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return agent_public_view(agent)


@router.patch("/{grn:path}")
async def update_agent(
    grn: str,
    body: AgentUpdateRequest,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    _require_same_org(context, grn)
    status = _parse_status(body.status)
    async with session_factory() as session:
        try:
            agent = await _service(session).update_agent(
                grn,
                updated_by=str(context.principal.id),
                org_id=context.organization,
                name=body.name,
                description=body.description,
                system_prompt=body.system_prompt,
                model_config=body.model_settings,
                allowed_tools=body.allowed_tools,
                knowledge_sources=body.knowledge_sources,
                status=status,
                metadata=body.metadata,
                correlation_id=str(context.correlation_id),
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return agent_public_view(agent)


@router.delete("/{grn:path}")
async def delete_agent(
    grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    _require_same_org(context, grn)
    async with session_factory() as session:
        try:
            await _service(session).delete_agent(
                grn,
                deleted_by=str(context.principal.id),
                org_id=context.organization,
                correlation_id=str(context.correlation_id),
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return {"deleted": True, "grn": grn}
