"""Mappers between Domain (KnowledgeSource) and Persistence (KnowledgeSourceORM)."""
from gabriel.knowledge.source_models import KnowledgeSource, KnowledgeSourceStatus
from gabriel.knowledge.source_orm import KnowledgeSourceORM
from gabriel.resource.grn import GRN


def orm_to_domain(orm: KnowledgeSourceORM) -> KnowledgeSource:
    """Convert ORM object to domain object (string GRN → GRN object)."""
    return KnowledgeSource(
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
        name=orm.name,
        description=orm.description or "",
        status=KnowledgeSourceStatus(orm.status),
        document_count=orm.document_count or 0,
    )


def domain_to_orm(domain: KnowledgeSource) -> KnowledgeSourceORM:
    """Convert domain object to ORM object (GRN object → string)."""
    return KnowledgeSourceORM(
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
        name=domain.name,
        description=domain.description,
        status=domain.status.value,
        document_count=domain.document_count,
    )
