"""Projection base class: Builds read models from events."""
from abc import ABC, abstractmethod

from gabriel.events.event import Event


class Projection(ABC):
    """Base class for projections.
    
    A projection subscribes to events and updates a read model.
    
    The write model (commands → handlers → events) never touches
    read tables directly. Instead, projections consume events and
    build read models from them.
    
    This separation enables:
    - Consistent audit trail (events are immutable)
    - Event replay (rebuild projections from scratch)
    - Multiple read models from the same event stream
    - Eventually consistent reads
    """

    @property
    @abstractmethod
    def event_types(self) -> list[str]:
        """Event types this projection subscribes to.
        
        Example: ['organization_created', 'organization_renamed']
        """
        pass

    @abstractmethod
    async def handle_event(self, event: Event) -> None:
        """Handle an event and update the read model.
        
        Args:
            event: The event to handle.
        """
        pass

    async def reset(self) -> None:
        """Reset the projection to initial state.
        
        Called during event replay to rebuild from scratch.
        Subclasses should override if they have internal state.
        """
        pass
