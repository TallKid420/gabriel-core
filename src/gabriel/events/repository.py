"""Event Repository: Persist and query events (ADR-017).

Implements the transactional outbox pattern for event persistence.
Events are append-only and queried by organization, resource, correlation_id,
and timestamp for audit trails and replays.
"""

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from gabriel.events.orm import EventORM
from gabriel.events.event import Event


class EventRepository:
    """Repository for persisting and querying events.
    
    This is the write-model side of CQRS: commands → handlers → events → repository.
    The repository implements the transactional outbox pattern:
    - Events are appended within the same transaction as resource creation
    - No separate "publish" step — events are durable immediately
    - Later upgrades to Kafka/NATS are transparent to callers
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize repository with async session.
        
        Args:
            session: SQLAlchemy AsyncSession for database operations.
        """
        self.session = session
    
    async def append(self, event: Event) -> EventORM:
        """Append a single event to the store (transactionally).
        
        Events are appended within the caller's transaction, enabling the
        outbox pattern: insert resource + insert event in one unit of work.
        Caller is responsible for calling session.commit().
        
        Args:
            event: The event domain object to persist.
            
        Returns:
            EventORM: The persisted event.
        """
        orm = EventORM(
            id=event.id,
            organization_id=event.organization_id,
            type=event.type,
            occurred_at=event.occurred_at,
            resource_grn=event.resource_grn,
            principal_id=event.principal_id,
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            payload=event.payload,
            event_metadata=event.metadata,
        )
        self.session.add(orm)
        # Caller commits the transaction
        return orm
    
    async def append_many(self, events: list[Event]) -> list[EventORM]:
        """Append multiple events to the store (transactionally).
        
        All events are added within one transaction. Caller is responsible
        for calling session.commit().
        
        Args:
            events: List of event domain objects.
            
        Returns:
            list[EventORM]: The persisted events.
        """
        orms = []
        for event in events:
            orm = EventORM(
                id=event.id,
                organization_id=event.organization_id,
                type=event.type,
                occurred_at=event.occurred_at,
                resource_grn=event.resource_grn,
                principal_id=event.principal_id,
                correlation_id=event.correlation_id,
                causation_id=event.causation_id,
                payload=event.payload,
                event_metadata=event.metadata,
            )
            self.session.add(orm)
            orms.append(orm)
        # Caller commits the transaction
        return orms
    
    async def get_by_id(self, event_id: str) -> EventORM | None:
        """Retrieve an event by its ID.
        
        Args:
            event_id: The event UUID.
            
        Returns:
            EventORM: The event, or None if not found.
        """
        result = await self.session.execute(
            select(EventORM).filter_by(id=event_id)
        )
        return result.scalar_one_or_none()
    
    async def events_for_organization(self, organization_id: str) -> list[EventORM]:
        """Get all events for an organization.
        
        Args:
            organization_id: The organization ID.
            
        Returns:
            list[EventORM]: All events for the organization, in occurred order.
        """
        result = await self.session.execute(
            select(EventORM)
            .filter_by(organization_id=organization_id)
            .order_by(EventORM.occurred_at)
        )
        return list(result.scalars().all())
    
    async def events_for_resource(self, resource_grn: str) -> list[EventORM]:
        """Get all events for a specific resource.
        
        Args:
            resource_grn: The resource GRN.
            
        Returns:
            list[EventORM]: All events for the resource, in occurred order.
        """
        result = await self.session.execute(
            select(EventORM)
            .filter_by(resource_grn=resource_grn)
            .order_by(EventORM.occurred_at)
        )
        return list(result.scalars().all())
    
    async def events_by_type(self, event_type: str) -> list[EventORM]:
        """Get all events of a specific type.
        
        Args:
            event_type: The event type (e.g., 'resource_created').
            
        Returns:
            list[EventORM]: All events of that type, in occurred order.
        """
        result = await self.session.execute(
            select(EventORM)
            .filter_by(type=event_type)
            .order_by(EventORM.occurred_at)
        )
        return list(result.scalars().all())
    
    async def events_for_principal(self, principal_id: str) -> list[EventORM]:
        """Get all events triggered by a principal.
        
        Args:
            principal_id: The principal ID.
            
        Returns:
            list[EventORM]: All events from that principal, in occurred order.
        """
        result = await self.session.execute(
            select(EventORM)
            .filter_by(principal_id=principal_id)
            .order_by(EventORM.occurred_at)
        )
        return list(result.scalars().all())
    
    async def events_by_correlation_id(self, correlation_id: str) -> list[EventORM]:
        """Get all events with a specific correlation ID (trace).
        
        Args:
            correlation_id: The correlation ID.
            
        Returns:
            list[EventORM]: All events with that correlation_id, in occurred order.
        """
        result = await self.session.execute(
            select(EventORM)
            .filter_by(correlation_id=correlation_id)
            .order_by(EventORM.occurred_at)
        )
        return list(result.scalars().all())
    
    async def events_since(self, since: datetime) -> list[EventORM]:
        """Get all events that occurred since a given timestamp.
        
        Useful for event sourcing replays or change data capture.
        
        Args:
            since: The datetime cutoff (inclusive).
            
        Returns:
            list[EventORM]: All events since that time, in occurred order.
        """
        result = await self.session.execute(
            select(EventORM)
            .filter(EventORM.occurred_at >= since)
            .order_by(EventORM.occurred_at)
        )
        return list(result.scalars().all())
    
    async def count_events(self, organization_id: str) -> int:
        """Get count of events for an organization.
        
        Args:
            organization_id: The organization ID.
            
        Returns:
            int: Number of events in the organization.
        """
        result = await self.session.execute(
            select(EventORM)
            .filter_by(organization_id=organization_id)
        )
        return len(result.scalars().all())
