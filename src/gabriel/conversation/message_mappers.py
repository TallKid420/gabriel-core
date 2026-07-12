"""Mappers between Domain (Message) and Persistence (MessageORM)."""
from gabriel.conversation.message_models import Message, MessageRole
from gabriel.conversation.message_orm import MessageORM
from gabriel.resource.grn import GRN


def orm_to_domain(orm: MessageORM) -> Message:
    """Convert ORM object to domain object (string GRN → GRN object)."""
    return Message(
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
        conversation_grn=orm.conversation_grn,
        role=MessageRole(orm.role),
        content=orm.content,
        prompt_tokens=orm.prompt_tokens,
        completion_tokens=orm.completion_tokens,
        total_tokens=orm.total_tokens,
        model=orm.model,
    )


def domain_to_orm(domain: Message) -> MessageORM:
    """Convert domain object to ORM object (GRN object → string)."""
    return MessageORM(
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
        conversation_grn=domain.conversation_grn,
        role=domain.role.value,
        content=domain.content,
        prompt_tokens=domain.prompt_tokens,
        completion_tokens=domain.completion_tokens,
        total_tokens=domain.total_tokens,
        model=domain.model,
    )
