"""
orm_to_domain and domain_to_orm: parse/serialize PrincipalID. 
Convert set[Capability] to/from list[str] for ORM storage.
"""

from gabriel.identity.principal import Principal
from gabriel.identity.principal_id import PrincipalID
from gabriel.identity.orm import PrincipalORM

def orm_to_domain(orm: PrincipalORM) -> Principal:
    """Convert a PrincipalORM to a Principal domain object."""
    return Principal(
        id=PrincipalID.parse(orm.principal_id),
        resource_grn=orm.resource_grn,
        organization_id=orm.org_id,
        principal_type=orm.principal_type,
        display_name=orm.display_name,
        status=orm.status,
        capabilities=set(orm.capabilities),
        metadata=orm.resource_metadata,
        created_at=orm.created_at,
        updated_at=orm.updated_at
    )

def domain_to_orm(domain: Principal) -> PrincipalORM:
    """Convert a Principal domain object to a PrincipalORM."""
    return PrincipalORM(
        principal_id=str(domain.id),
        org_id=domain.organization_id,
        principal_type=domain.principal_type,
        display_name=domain.display_name,
        status=domain.status,
        capabilities=list(domain.capabilities),
        resource_grn=domain.resource_grn,
        resource_metadata=domain.metadata,
        created_at=domain.created_at,
        updated_at=domain.updated_at
    )