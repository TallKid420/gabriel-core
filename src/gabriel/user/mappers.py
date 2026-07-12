"""Mappers between Domain (User) and Persistence (UserORM)."""
from gabriel.resource.grn import GRN
from gabriel.user.models import User
from gabriel.user.orm import UserORM


def orm_to_domain(orm: UserORM) -> User:
    """Convert ORM object to domain object (string GRN → GRN object)."""
    return User(
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
        email=orm.email,
        display_name=orm.display_name,
        principal_id=orm.principal_id,
        password_hash=orm.password_hash,
    )


def domain_to_orm(domain: User) -> UserORM:
    """Convert domain object to ORM object (GRN object → string)."""
    return UserORM(
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
        email=domain.email,
        display_name=domain.display_name,
        principal_id=domain.principal_id,
        password_hash=domain.password_hash,
    )
