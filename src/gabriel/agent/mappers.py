"""Mappers between Domain (Agent) and Persistence (AgentORM)."""

from gabriel.agent.models import Agent
from gabriel.agent.orm import AgentORM
from gabriel.agent.specification import AgentSpecification
from gabriel.resource.grn import GRN


def orm_to_domain(orm: AgentORM) -> Agent:
    """Convert ORM object to domain object."""
    return Agent(
        grn=GRN.parse(orm.grn),
        org_id=orm.org_id,
        resource_type=orm.resource_type,
        state=orm.state,
        version=orm.version,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
        created_by=orm.created_by,
        updated_by=orm.updated_by,
        metadata=orm.resource_metadata,
        labels=orm.labels,
        specification=AgentSpecification.model_validate(orm.specification or {}),
        enabled=orm.enabled,
    )


def domain_to_orm(domain: Agent) -> AgentORM:
    """Convert domain object to ORM object."""
    return AgentORM(
        grn=str(domain.grn),
        org_id=domain.org_id,
        resource_type=domain.resource_type,
        state=domain.state,
        version=domain.version,
        created_at=domain.created_at,
        updated_at=domain.updated_at,
        created_by=domain.created_by,
        updated_by=domain.updated_by,
        resource_metadata=domain.metadata,
        labels=domain.labels,
        specification=domain.specification.model_dump(mode="json"),
        enabled=domain.enabled,
    )
