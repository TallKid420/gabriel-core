"""Mappers between Domain (MemoryLayerEntry) and Persistence (MemoryLayerEntryORM)."""
from gabriel.memory.layer_models import MemoryLayerEntry, MemoryScope
from gabriel.memory.layer_orm import MemoryLayerEntryORM
from gabriel.resource.grn import GRN


def orm_to_domain(orm: MemoryLayerEntryORM) -> MemoryLayerEntry:
    """Convert ORM object to domain object (string GRN → GRN object)."""
    return MemoryLayerEntry(
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
        key=orm.key,
        value=orm.value,
        scope=MemoryScope(orm.scope),
        subject_grn=orm.subject_grn,
        tags=list(orm.tags or []),
        expires_at=orm.expires_at,
    )


def domain_to_orm(domain: MemoryLayerEntry) -> MemoryLayerEntryORM:
    """Convert domain object to ORM object (GRN object → string)."""
    return MemoryLayerEntryORM(
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
        key=domain.key,
        value=domain.value,
        scope=domain.scope.value,
        subject_grn=domain.subject_grn,
        tags=domain.tags,
        expires_at=domain.expires_at,
    )
