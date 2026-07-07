"""Agent lifecycle service."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from gabriel.agent.mappers import domain_to_orm, orm_to_domain
from gabriel.agent.models import Agent
from gabriel.agent.repository import AgentRepository
from gabriel.agent.specification import AgentSpecification
from gabriel.events.event import Event
from gabriel.events.repository import EventRepository
from gabriel.resource.bootstrap import register_core_resource_types
from gabriel.resource.exceptions import DuplicateResourceError
from gabriel.resource.factory import ResourceFactory
from gabriel.resource.grn import GRN
from gabriel.resource.models import ResourceState
from gabriel.resource.registry import registry


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentService:
    """Business logic for persisted Agent resources."""

    def __init__(self, repository: AgentRepository, event_repo: EventRepository | None = None):
        register_core_resource_types()
        self.repo = repository
        self.event_repo = event_repo
        self.factory = ResourceFactory(registry)

    async def create_agent(
        self,
        org_id: str,
        created_by: str,
        specification: AgentSpecification,
        *,
        agent_grn: str | None = None,
        enabled: bool = True,
        metadata: dict | None = None,
        labels: dict[str, str] | None = None,
        correlation_id: str | None = None,
    ) -> Agent:
        grn = GRN.parse(agent_grn) if agent_grn else GRN.generate(org_id, "agent")
        grn_str = str(grn)

        domain_agent = self.factory.create(
            "agent",
            grn=grn,
            org_id=org_id,
            created_by=created_by,
            specification=specification,
            enabled=enabled,
            metadata=metadata or {},
            labels=labels or {},
        )

        try:
            persisted_orm = await self.repo.create(domain_to_orm(domain_agent))
            if self.event_repo is not None:
                await self.event_repo.append(
                    Event(
                        type="resource_created",
                        principal_id=created_by,
                        organization_id=org_id,
                        resource_grn=grn_str,
                        correlation_id=correlation_id,
                        payload={"resource_type": "agent", "grn": grn_str},
                        metadata={"service": "AgentService", "operation": "create_agent"},
                    )
                )
                await self.repo.session.commit()
            return orm_to_domain(persisted_orm)
        except IntegrityError as exc:
            raise DuplicateResourceError(f"Agent with GRN '{grn_str}' already exists.") from exc

    async def get_agent(self, grn_str: str) -> Agent:
        return orm_to_domain(await self.repo.get_by_grn(grn_str))

    async def list_agents(self, org_id: str | None = None) -> list[Agent]:
        orm_agents = await self.repo.list_for_org(org_id) if org_id else await self.repo.list_all()
        return [orm_to_domain(agent) for agent in orm_agents]

    async def update_agent(
        self,
        grn_str: str,
        updated_by: str,
        *,
        specification: AgentSpecification | None = None,
        enabled: bool | None = None,
        correlation_id: str | None = None,
    ) -> Agent:
        existing = orm_to_domain(await self.repo.get_by_grn(grn_str))

        updated = existing.model_copy(
            update={
                "specification": specification or existing.specification,
                "enabled": existing.enabled if enabled is None else enabled,
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
                    payload={"resource_type": "agent", "grn": grn_str},
                    metadata={"service": "AgentService", "operation": "update_agent"},
                )
            )
            await self.repo.session.commit()
        return orm_to_domain(persisted)

    async def delete_agent(
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
                    payload={"resource_type": "agent", "grn": grn_str},
                    metadata={"service": "AgentService", "operation": "delete_agent"},
                )
            )
            await self.repo.session.commit()
