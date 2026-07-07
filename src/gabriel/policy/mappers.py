"""Mappers between Domain (Policy) and Persistence (PolicyORM)."""

from gabriel.policy.models import Policy, PolicyStatement
from gabriel.policy.orm import PolicyORM
from gabriel.resource.grn import GRN


def orm_to_domain(orm: PolicyORM) -> Policy:
    """Convert ORM object to domain object."""
    return Policy(
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
        statements=[PolicyStatement.model_validate(item) for item in (orm.statements or [])],
    )


def domain_to_orm(domain: Policy) -> PolicyORM:
    """Convert domain object to ORM object."""
    return PolicyORM(
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
        statements=[statement.model_dump(mode="json") for statement in domain.statements],
    )
