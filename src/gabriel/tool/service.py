"""ToolService — business logic for the Tool resource."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError

from gabriel.events.event import Event
from gabriel.events.repository import EventRepository
from gabriel.resource.bootstrap import register_core_resource_types
from gabriel.resource.exceptions import DuplicateResourceError
from gabriel.resource.factory import ResourceFactory
from gabriel.resource.grn import GRN
from gabriel.resource.models import ResourceState
from gabriel.resource.registry import registry
from gabriel.tool.mappers import domain_to_orm, orm_to_domain
from gabriel.tool.models import ExecutionRuntime, SafetyLevel, Tool, ToolCategory
from gabriel.tool.repository import ToolRepository
from gabriel.tool.discovery import ToolLibraryIndexer


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ToolService:
    """Business logic for Tools.

    Responsibilities
    ----------------
    - Accepts and returns Domain objects (Tool, not ToolORM).
    - Uses the repository as an internal persistence detail.
    - Never exposes ORM models to callers.
    - Emits resource lifecycle events transactionally (ADR-017).
    """

    def __init__(
        self,
        repository: ToolRepository,
        event_repo: EventRepository | None = None,
    ) -> None:
        register_core_resource_types()
        self.repo = repository
        self.event_repo = event_repo
        self.factory = ResourceFactory(registry)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_tool(
        self,
        org_id: str,
        created_by: str,
        *,
        name: str,
        description: str,
        category: ToolCategory,
        parameters: dict[str, Any],
        safety_level: SafetyLevel,
        runtime_binding: str = "",
        execution_runtime: ExecutionRuntime = ExecutionRuntime.LOCAL,
        enabled: bool = True,
        configuration: dict[str, Any] | None = None,
        tool_grn: str | None = None,
        metadata: dict[str, Any] | None = None,
        labels: dict[str, str] | None = None,
        correlation_id: str | None = None,
        fn: Any | None = None,
    ) -> Tool:
        grn = GRN.parse(tool_grn) if tool_grn else GRN.generate(org_id, "tool")
        grn_str = str(grn)

        domain_tool = self.factory.create(
            "tool",
            grn=grn,
            org_id=org_id,
            created_by=created_by,
            name=name,
            description=description,
            category=category,
            parameters=parameters,
            safety_level=safety_level,
            runtime_binding=runtime_binding,
            execution_runtime=execution_runtime,
            enabled=enabled,
            configuration=configuration or {},
            labels=labels or {},
            metadata=metadata or {},
            fn=fn or None,
        )

        try:
            persisted_orm = await self.repo.create(domain_to_orm(domain_tool))
            if self.event_repo is not None:
                await self.event_repo.append(
                    Event(
                        type="resource_created",
                        principal_id=created_by,
                        organization_id=org_id,
                        resource_grn=grn_str,
                        correlation_id=correlation_id,
                        payload={"resource_type": "tool", "grn": grn_str},
                        metadata={"service": "ToolService", "operation": "create_tool"},
                    )
                )
                await self.repo.session.commit()
            return orm_to_domain(persisted_orm)
        except IntegrityError as exc:
            raise DuplicateResourceError(
                f"Tool with GRN '{grn_str}' already exists."
            ) from exc

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_tool(self, grn_str: str) -> Tool:
        orm_tool = await self.repo.get_by_grn(grn_str)
        return orm_to_domain(orm_tool)

    async def get_tool_by_name(self, org_id: str, name: str) -> Tool | None:
        """Return a Tool by org + name slug, or ``None`` if not found."""
        tools = await self.repo.list_for_org(org_id)
        for t in tools:
            if t.name == name:
                return orm_to_domain(t)
        return None

    async def list_tools(
        self,
        org_id: str | None = None,
        category: ToolCategory | None = None,
    ) -> list[Tool]:
        if org_id:
            orm_tools = await self.repo.list_for_org(org_id)
        else:
            orm_tools = await self.repo.list_all()

        tools = ToolLibraryIndexer().discover(force=True)
        for t in orm_tools:
            tools.append(orm_to_domain(t))

        if category is not None:
            tools = [t for t in tools if t.category == category]
        return tools

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_tool(
        self,
        grn_str: str,
        updated_by: str,
        *,
        name: str | None = None,
        description: str | None = None,
        category: ToolCategory | None = None,
        fn: Any | None = None,
        parameters: dict[str, Any] | None = None,
        safety_level: SafetyLevel | None = None,
        runtime_binding: str | None = None,
        execution_runtime: ExecutionRuntime | None = None,
        enabled: bool | None = None,
        configuration: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> Tool:
        existing = orm_to_domain(await self.repo.get_by_grn(grn_str))

        # model_copy(update=...) bypasses pydantic validation, so coerce enum
        # inputs (raw strings/ints are accepted for convenience) explicitly.
        if category is not None:
            category = ToolCategory(category)
        if safety_level is not None:
            safety_level = SafetyLevel(safety_level)
        if execution_runtime is not None:
            execution_runtime = ExecutionRuntime(execution_runtime)

        updated = existing.model_copy(
            update={
                "name": name if name is not None else existing.name,
                "description": (
                    description if description is not None else existing.description
                ),
                "category": category if category is not None else existing.category,
                "parameters": (
                    parameters if parameters is not None else existing.parameters
                ),
                "safety_level": (
                    safety_level if safety_level is not None else existing.safety_level
                ),
                "runtime_binding": (
                    runtime_binding
                    if runtime_binding is not None
                    else existing.runtime_binding
                ),
                "execution_runtime": (
                    execution_runtime
                    if execution_runtime is not None
                    else existing.execution_runtime
                ),
                "enabled": enabled if enabled is not None else existing.enabled,
                "configuration": (
                    configuration
                    if configuration is not None
                    else existing.configuration
                ),
                "updated_by": updated_by,
                "updated_at": _utcnow(),
                "version": existing.version + 1,
                "state": ResourceState.ACTIVE,
            }
        )

        persisted = await self.repo.update(domain_to_orm(updated))
        if self.event_repo is not None:
            await self.event_repo.append(
                Event(
                    type="resource_updated",
                    principal_id=updated_by,
                    organization_id=existing.org_id,
                    resource_grn=grn_str,
                    correlation_id=correlation_id,
                    payload={"resource_type": "tool", "grn": grn_str},
                    metadata={"service": "ToolService", "operation": "update_tool"},
                )
            )
            await self.repo.session.commit()
        return orm_to_domain(persisted)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_tool(
        self,
        grn_str: str,
        deleted_by: str,
        *,
        correlation_id: str | None = None,
    ) -> None:
        existing = orm_to_domain(await self.repo.get_by_grn(grn_str))
        await self.repo.delete(grn_str)
        if self.event_repo is not None:
            await self.event_repo.append(
                Event(
                    type="resource_deleted",
                    principal_id=deleted_by,
                    organization_id=existing.org_id,
                    resource_grn=grn_str,
                    correlation_id=correlation_id,
                    payload={"resource_type": "tool", "grn": grn_str},
                    metadata={"service": "ToolService", "operation": "delete_tool"},
                )
            )
            await self.repo.session.commit()
