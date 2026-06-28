"""EventStore: Append-only event log."""
from gabriel.events.event import Event
from gabriel.events.exceptions import InvalidEventError


class EventStore:
    """Append-only event store.
    
    In Gabriel, the event store is the source of truth.
    Events are never updated or deleted — only appended.
    
    This implementation is in-process (in-memory).
    Later implementations could use Postgres, EventStoreDB, or other backends
    without changing the interface.
    """

    def __init__(self):
        """Initialize an empty event store."""
        self._events: list[Event] = []

    def append(self, event: Event) -> None:
        """Append an event to the store.
        
        Args:
            event: The event to append.
            
        Raises:
            InvalidEventError: If event is invalid.
        """
        if not event:
            raise InvalidEventError("Cannot append None event")
        self._events.append(event)

    def append_many(self, events: list[Event]) -> None:
        """Append multiple events to the store.
        
        Args:
            events: Events to append.
        """
        for event in events:
            self.append(event)

    def events(self) -> list[Event]:
        """Get all events in order.
        
        Returns:
            list[Event]: All events, in append order.
        """
        return list(self._events)

    def events_for_organization(self, organization_id: str) -> list[Event]:
        """Get all events for an organization.
        
        Args:
            organization_id: The organization ID to query.
            
        Returns:
            list[Event]: All events belonging to the organization.
        """
        return [e for e in self._events if e.organization_id == organization_id]

    def events_for_resource(self, resource_grn: str) -> list[Event]:
        """Get all events for a specific resource.
        
        Args:
            resource_grn: The resource GRN to query.
            
        Returns:
            list[Event]: All events for the resource.
        """
        return [e for e in self._events if e.resource_grn == resource_grn]

    def events_by_type(self, event_type: str) -> list[Event]:
        """Get all events of a specific type.
        
        Args:
            event_type: The event type to query.
            
        Returns:
            list[Event]: All events of that type.
        """
        return [e for e in self._events if e.type == event_type]

    def events_for_principal(self, principal_id: str) -> list[Event]:
        """Get all events triggered by a principal.
        
        Args:
            principal_id: The principal ID.
            
        Returns:
            list[Event]: All events from that principal.
        """
        return [e for e in self._events if e.principal_id == principal_id]

    def events_by_correlation_id(self, correlation_id: str) -> list[Event]:
        """Get all events with a specific correlation ID (trace).
        
        Args:
            correlation_id: The correlation ID.
            
        Returns:
            list[Event]: All events in the trace.
        """
        return [e for e in self._events if e.correlation_id == correlation_id]

    def count(self) -> int:
        """Get total number of events.
        
        Returns:
            int: Number of events in store.
        """
        return len(self._events)

    def clear(self) -> None:
        """Clear all events (useful for testing)."""
        self._events.clear()
