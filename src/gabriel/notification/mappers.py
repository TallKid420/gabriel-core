"""Mappers between Domain (Notification) and Persistence (NotificationORM)."""
from gabriel.notification.models import Notification
from gabriel.notification.orm import NotificationORM
from gabriel.resource.grn import GRN


def orm_to_domain(orm: NotificationORM) -> Notification:
    """Convert ORM object to domain object (string GRN → GRN object)."""
    return Notification(
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
        recipient=orm.recipient,
        type=orm.type,
        title=orm.title,
        body=orm.body,
        read=orm.read,
        read_at=orm.read_at,
        source_event_id=orm.source_event_id,
    )


def domain_to_orm(domain: Notification) -> NotificationORM:
    """Convert domain object to ORM object (GRN object → string)."""
    return NotificationORM(
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
        recipient=domain.recipient,
        type=domain.type,
        title=domain.title,
        body=domain.body,
        read=domain.read,
        read_at=domain.read_at,
        source_event_id=domain.source_event_id,
    )
