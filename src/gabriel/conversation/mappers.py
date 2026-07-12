"""Mappers between Domain (Conversation) and Persistence (ConversationORM)."""
from gabriel.conversation.models import Conversation, ConversationStatus
from gabriel.conversation.orm import ConversationORM
from gabriel.resource.grn import GRN


def orm_to_domain(orm: ConversationORM) -> Conversation:
    """Convert ORM object to domain object (string GRN → GRN object)."""
    return Conversation(
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
        title=orm.title,
        status=ConversationStatus(orm.status),
        participants=list(orm.participants or []),
        agent_grn=orm.agent_grn,
    )


def domain_to_orm(domain: Conversation) -> ConversationORM:
    """Convert domain object to ORM object (GRN object → string)."""
    return ConversationORM(
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
        title=domain.title,
        status=domain.status.value,
        participants=domain.participants,
        agent_grn=domain.agent_grn,
    )
