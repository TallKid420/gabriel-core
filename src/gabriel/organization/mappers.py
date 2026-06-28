"""Mappers between Domain (Organization) and Persistence (OrganizationORM)."""
from gabriel.organization.models import Organization
from gabriel.organization.orm import OrganizationORM
from gabriel.resource.grn import GRN


def orm_to_domain(orm: OrganizationORM) -> Organization:
    """Convert ORM object to domain object.
    
    The ORM stores GRN as a string; we parse it back to the domain GRN object.
    Only the persistence layer sees VARCHAR; the domain never does.
    """
    grn = GRN.parse(orm.grn)  # Deserialize string → GRN domain object
    return Organization(
        grn=grn,
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
        display_name=orm.display_name,
        description=orm.description,
    )


def domain_to_orm(domain: Organization) -> OrganizationORM:
    """Convert domain object to ORM object.
    
    The domain has a GRN object; we serialize it to a string for storage.
    """
    return OrganizationORM(
        grn=str(domain.grn),  # Serialize GRN domain object → string
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
        display_name=domain.display_name,
        description=domain.description,
    )
