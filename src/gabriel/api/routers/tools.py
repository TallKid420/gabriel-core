"""Tools router (org-scoped, DB-backed).

    POST   /tools               — register a tool
    GET    /tools               — list tools (?category=&enabled=&execution_runtime=)
    GET    /tools/{grn}         — fetch a tool
    PATCH  /tools/{grn}         — update a tool (incl. enable/disable toggle)
    DELETE /tools/{grn}         — delete a tool

Tools are Universal Resources (ADR-009 / ADR-016): org-scoped, GRN-addressed,
versioned, with metadata and labels. The ``execution_runtime`` field is a V1
declaration only (local/enterprise/cloud/edge) — no routing engine consumes
it yet. The chat runtime honours the ``enabled`` flag when resolving which
tools an agent may use.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gabriel.api.dependencies import get_db_session_factory, get_execution_context
from gabriel.api.errors import GabrielAPIError
from gabriel.api.tenancy import require_same_org
from gabriel.events.repository import EventRepository
from gabriel.resource.exceptions import DuplicateResourceError, ResourceNotFoundError
from gabriel.runtime.context import ExecutionContext
from gabriel.tool.models import ExecutionRuntime, SafetyLevel, ToolCategory
from gabriel.tool.repository import ToolRepository
from gabriel.tool.service import ToolService

router = APIRouter(prefix="/tools", tags=["Tools"])


class ToolCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    description: str = ""
    category: str = Field(min_length=1)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    safety_level: int = 0
    required_capabilities: list[str] = Field(default_factory=list)
    runtime_binding: str = ""
    execution_runtime: str = "local"
    enabled: bool = True
    configuration: dict[str, Any] = Field(default_factory=dict)
    metadata: dict | None = None
    labels: dict[str, str] | None = None


class ToolUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    safety_level: int | None = None
    required_capabilities: list[str] | None = None
    runtime_binding: str | None = None
    execution_runtime: str | None = None
    enabled: bool | None = None
    configuration: dict[str, Any] | None = None


def _parse_category(value: str | None) -> ToolCategory | None:
    if value is None:
        return None
    try:
        return ToolCategory(value)
    except ValueError as exc:
        raise GabrielAPIError(
            f"Unknown tool category '{value}'", status_code=422
        ) from exc


def _parse_runtime(value: str | None) -> ExecutionRuntime | None:
    if value is None:
        return None
    try:
        return ExecutionRuntime(value)
    except ValueError as exc:
        raise GabrielAPIError(
            f"Unknown execution runtime '{value}'", status_code=422
        ) from exc


def _parse_safety(value: int | None) -> SafetyLevel | None:
    if value is None:
        return None
    try:
        return SafetyLevel(value)
    except ValueError as exc:
        raise GabrielAPIError(
            f"Unknown safety level '{value}'", status_code=422
        ) from exc


def _service(session) -> ToolService:
    return ToolService(ToolRepository(session), EventRepository(session))


@router.post("", status_code=201)
async def create_tool(
    body: ToolCreateRequest,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    category = _parse_category(body.category)
    runtime = _parse_runtime(body.execution_runtime)
    safety = _parse_safety(body.safety_level)
    async with session_factory() as session:
        try:
            tool = await _service(session).create_tool(
                context.organization,
                str(context.principal.id),
                name=body.name,
                description=body.description,
                category=category,
                input_schema=body.input_schema,
                output_schema=body.output_schema,
                safety_level=safety,
                required_capabilities=body.required_capabilities,
                runtime_binding=body.runtime_binding,
                execution_runtime=runtime,
                enabled=body.enabled,
                configuration=body.configuration,
                metadata=body.metadata,
                labels=body.labels,
                correlation_id=str(context.correlation_id),
            )
        except DuplicateResourceError as exc:
            raise GabrielAPIError(str(exc), status_code=409) from exc
        return tool.public_view()


@router.get("")
async def list_tools(
    category: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    execution_runtime: str | None = Query(default=None),
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    parsed_category = _parse_category(category)
    parsed_runtime = _parse_runtime(execution_runtime)
    async with session_factory() as session:
        tools = await _service(session).list_tools(
            context.organization, category=parsed_category
        )
        if enabled is not None:
            tools = [t for t in tools if t.enabled == enabled]
        if parsed_runtime is not None:
            tools = [t for t in tools if t.execution_runtime == parsed_runtime]
        return {
            "items": [tool.public_view() for tool in tools],
            "total": len(tools),
        }


@router.get("/{grn:path}")
async def get_tool(
    grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    require_same_org(context, grn)
    async with session_factory() as session:
        try:
            tool = await _service(session).get_tool(grn)
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return tool.public_view()


@router.patch("/{grn:path}")
async def update_tool(
    grn: str,
    body: ToolUpdateRequest,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    require_same_org(context, grn)
    category = _parse_category(body.category)
    runtime = _parse_runtime(body.execution_runtime)
    safety = _parse_safety(body.safety_level)
    async with session_factory() as session:
        try:
            tool = await _service(session).update_tool(
                grn,
                str(context.principal.id),
                name=body.name,
                description=body.description,
                category=category,
                input_schema=body.input_schema,
                output_schema=body.output_schema,
                safety_level=safety,
                required_capabilities=body.required_capabilities,
                runtime_binding=body.runtime_binding,
                execution_runtime=runtime,
                enabled=body.enabled,
                configuration=body.configuration,
                correlation_id=str(context.correlation_id),
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return tool.public_view()


@router.delete("/{grn:path}", status_code=204)
async def delete_tool(
    grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    require_same_org(context, grn)
    async with session_factory() as session:
        try:
            await _service(session).delete_tool(
                grn,
                str(context.principal.id),
                correlation_id=str(context.correlation_id),
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
    return None
