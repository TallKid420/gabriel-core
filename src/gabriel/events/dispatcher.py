"""Dispatcher: Routes commands to handlers, stores events, updates projections."""
from gabriel.events.command import Command
from gabriel.events.event import Event
from gabriel.events.handler import Handler
from gabriel.events.event_store import EventStore
from gabriel.events.projection import Projection
from gabriel.events.exceptions import HandlerNotFoundError


class Dispatcher:
    """Orchestrates the CQRS flow.
    
    Flow:
      1. Receive command
      2. Find handler for command.type
      3. Execute handler → get events
      4. Append events to event store
      5. Notify projections
    
    This is the heart of Gabriel's event backbone.
    """

    def __init__(self, event_store: EventStore):
        """Initialize dispatcher.
        
        Args:
            event_store: The event store to append events to.
        """
        self.event_store = event_store
        self._handlers: dict[str, Handler] = {}
        self._projections: list[Projection] = []

    def register_handler(self, handler: Handler) -> None:
        """Register a handler for a command type.
        
        Args:
            handler: The handler to register.
        """
        self._handlers[handler.command_type] = handler

    def register_projection(self, projection: Projection) -> None:
        """Register a projection to receive events.
        
        Args:
            projection: The projection to register.
        """
        self._projections.append(projection)

    async def dispatch(self, command: Command) -> list[Event]:
        """Dispatch a command.
        
        1. Finds handler for command.type
        2. Executes handler
        3. Stores events
        4. Notifies projections
        
        Args:
            command: The command to dispatch.
            
        Returns:
            list[Event]: Events emitted by the handler.
            
        Raises:
            HandlerNotFoundError: If no handler registered for command type.
            CommandValidationError: If command validation fails.
            HandlerExecutionError: If handler fails.
        """
        # 1. Find handler
        handler = self._handlers.get(command.type)
        if not handler:
            raise HandlerNotFoundError(
                f"No handler registered for command type '{command.type}'"
            )

        # 2. Execute handler
        events = await handler.handle(command)

        # 3. Store events
        self.event_store.append_many(events)

        # 4. Notify projections
        for event in events:
            await self._notify_projections(event)

        return events

    async def _notify_projections(self, event: Event) -> None:
        """Notify all subscribed projections of an event.
        
        Args:
            event: The event to notify projections about.
        """
        for projection in self._projections:
            if event.type in projection.event_types:
                await projection.handle_event(event)

    async def replay_events(self, events: list[Event]) -> None:
        """Replay events to projections (for rebuilding read models).
        
        Args:
            events: Events to replay.
        """
        # Reset projections first
        for projection in self._projections:
            await projection.reset()

        # Replay each event
        for event in events:
            await self._notify_projections(event)
