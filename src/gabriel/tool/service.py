from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone

from gabriel.events.event import Event
from gabriel.events.repository import EventRepository
from gabriel.resource.bootstrap import register_core_resource_types
from gabriel.resource.exceptions import DuplicateResourceError
from gabriel.resource.factory import ResourceFactory
from gabriel.resource.grn import GRN
from gabriel.resource.models import ResourceState
from gabriel.resource.registry import registry
from gabriel.tool.mappers import domain_to_orm, orm_to_domain
from gabriel.tool.models import Tool
from gabriel.tool.repository import ToolRepository


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class ToolService:
    """Business logic for Tools.
    
    This service:
    - Accepts and returns Domain objects (Tool, not ToolORM)
    - Uses the repository (internal persistence layer) privately
    - Never exposes ORM models to callers
    - Emits events transactionally (ADR-017 outbox pattern)
    """

    def __init__(self, repository: ToolRepository, event_repo: EventRepository | None = None):
        register_core_resource_types()
        self.repo = repository
        self.event_repo = event_repo
        self.factory = ResourceFactory(registry)

    async def create_tool(
        self,
        org_id: str,
        created_by: str,
        *,
        name: str,
        description: str,
        category: str,
        input_schema: dict,
        output_schema: dict,
        safety_level: int,
        required_capabilities: list[str],
        tool_grn: str | None = None,
        metadata: dict | None = None,
        labels: dict[str, str] | None = None,
        correlation_id: str | None = None,
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
            input_schema=input_schema,
            output_schema=output_schema,
            safety_level=safety_level,
            required_capabilities=required_capabilities,
            labels=labels or {},
            metadata=metadata or {},
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
            raise DuplicateResourceError(f"Tool with GRN '{grn_str}' already exists.") from exc

    async def get_tool(self, grn_str: str) -> Tool:
        orm_tool = await self.repo.get_by_grn(grn_str)
        return orm_to_domain(orm_tool)

    async def list_tools(self, org_id: str | None = None) -> list[Tool]:
        orm_tools = await self.repo.list_for_org(org_id) if org_id else await self.repo.list_all()
        return [orm_to_domain(tool) for tool in orm_tools]

    async def update_tool(
        self,
        grn_str: str,
        updated_by: str,
        *,
        name: str | None = None,
        description: str | None = None,
        category: str | None = None,
        input_schema: dict | None = None,
        output_schema: dict | None = None,
        safety_level: int | None = None,
        required_capabilities: list[str] | None = None,
        correlation_id: str | None = None,
    ) -> Tool:
        existing = orm_to_domain(await self.repo.get_by_grn(grn_str))

        updated = existing.model_copy(
            update={
                "name": name if name is not None else existing.name,
                "description": description if description is not None else existing.description,
                "category": category if category is not None else existing.category,
                "input_schema": input_schema if input_schema is not None else existing.input_schema,
                "output_schema": output_schema if output_schema is not None else existing.output_schema,
                "safety_level": safety_level if safety_level is not None else existing.safety_level,
                "required_capabilities": (
                    required_capabilities
                    if required_capabilities is not None
                    else existing.required_capabilities
                ),
                "updated_by": updated_by,
                "updated_at": utcnow(),
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