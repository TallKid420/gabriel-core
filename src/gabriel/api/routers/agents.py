from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from gabriel.runtime.context import ExecutionContext
from gabriel.api.services.agents import AgentService
from gabriel.api.dependencies import (
    GatewayService, 
    build_command, 
    get_agent_service, 
    get_execution_context, 
    get_gateway_service
)
from gabriel.api.schema import (
    AgentCreateRequest,  
    AgentSummaryResponse, 
    AgentStateResponse,
    AgentExecuteRequest,
    ResourceResponse, 
    ResourceDeleteResponse
)


router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("", response_model=list[AgentSummaryResponse])
async def list_agents(
    context: ExecutionContext = Depends(get_execution_context),
    service: AgentService = Depends(get_agent_service),
) -> list[AgentSummaryResponse]:
    agents = service.list_available_agents(context.principal)
    return [
        AgentSummaryResponse(
            id=agent.id,
            name=agent.name,
            description=agent.description,
            status=agent.status,
            icon=agent.icon,
            category=agent.category,
            provider=agent.provider,
            model=agent.model,
            enabled=agent.enabled,
        )
        for agent in agents
    ]


@router.post("", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    payload: AgentCreateRequest,
    context: ExecutionContext = Depends(get_execution_context),
    service: GatewayService = Depends(get_gateway_service),
) -> ResourceResponse:
    command = build_command(
        context,
        "create_agent",
        {
            "resource_type": "agent",
            "attributes": {
                "name": payload.name,
                "runtime": payload.runtime,
                "config": payload.config,
            },
        },
        action_name="agent:create",
    )
    events = await service.dispatch_command(command, context)
    created = events[0]
    return ResourceResponse(
        grn=created.payload["grn"],
        resource_type="agent",
        state="active",
        attributes=created.payload.get("attributes", {}),
    )

@router.delete("/{grn:path}", response_model=ResourceDeleteResponse)
async def delete_agent(
    grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    service: GatewayService = Depends(get_gateway_service),
) -> ResourceDeleteResponse:
    command = build_command(
        context=context,
        command_type="delete_agent",
        payload={"grn": grn},
        action_name="agent:delete",
        target_resource_grn=grn,
    )
    events = await service.dispatch_command(command, context)
    return ResourceDeleteResponse(deleted=True, grn=grn)

@router.get("/{grn:path}", response_model=ResourceResponse)
async def get_agent(
    grn: str,
    service: GatewayService = Depends(get_gateway_service),
) -> ResourceResponse:
    agent = service.get_agent(grn)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return ResourceResponse(
        grn=agent["grn"],
        resource_type="agent",
        state=agent.get("state", "active"),
        attributes=agent.get("attributes", {}),
    )


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
