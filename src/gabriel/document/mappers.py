"""Mappers between Domain (Document) and Persistence (DocumentORM)."""
from gabriel.document.models import Document, DocumentStatus
from gabriel.document.orm import DocumentORM
from gabriel.resource.grn import GRN


def orm_to_domain(orm: DocumentORM) -> Document:
    """Convert ORM object to domain object (string GRN → GRN object)."""
    return Document(
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
        filename=orm.filename,
        source_uri=orm.source_uri,
        media_type=orm.media_type,
        content_hash=orm.content_hash,
        byte_size=orm.byte_size,
        content_pointer=orm.content_pointer,
        raw_pointer=orm.raw_pointer,
        status=DocumentStatus(orm.status),
        chunk_count=orm.chunk_count,
        knowledge_source_grn=orm.knowledge_source_grn,
    )


def domain_to_orm(domain: Document) -> DocumentORM:
    """Convert domain object to ORM object (GRN object → string)."""
    return DocumentORM(
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
        filename=domain.filename,
        source_uri=domain.source_uri,
        media_type=domain.media_type,
        content_hash=domain.content_hash,
        byte_size=domain.byte_size,
        content_pointer=domain.content_pointer,
        raw_pointer=domain.raw_pointer,
        status=domain.status.value,
        chunk_count=domain.chunk_count,
        knowledge_source_grn=domain.knowledge_source_grn,
    )
