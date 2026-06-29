"""Dispatcher: Routes commands to handlers, stores events, updates projections."""
from gabriel.events.command import Command
from gabriel.events.event import Event
from gabriel.events.handler import Handler
from gabriel.events.event_store import EventStore
from gabriel.events.projection import Projection
from gabriel.events.exceptions import HandlerNotFoundError
from gabriel.runtime.context import ExecutionContext

import asyncio


class Dispatcher:
    """Orchestrates the CQRS flow with optional PEEL authorization.

    Flow:
      1. Receive command + context
      2. [PEEL] Authorize action (if PEEL enabled)
      3. Find handler for command.type
      4. Execute handler → get events
      5. Append events to event store
      6. Notify projections + listeners
    """

    def __init__(self, event_store: EventStore, peel=None):
        self.event_store = event_store
        self.peel = peel
        self._handlers: dict[str, Handler] = {}
        self._projections: list[Projection] = []
        self._listeners: list[asyncio.Queue] = []

    # -------------------------------------------------------------------------
    # Streaming
    # -------------------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        """Create a new subscription queue for real-time events."""
        queue: asyncio.Queue = asyncio.Queue()
        self._listeners.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Remove a subscription queue."""
        if queue in self._listeners:
            self._listeners.remove(queue)

    async def publish(self, event: Event) -> None:
        """Publish an event directly to all real-time listeners.

        Use this when you want to push an event without going through
        the full command dispatch cycle (e.g. from a LangGraph node).
        Does NOT write to the event store or notify projections.
        """
        for queue in self._listeners:
            await queue.put(event)

    # -------------------------------------------------------------------------
    # Registration
    # -------------------------------------------------------------------------

    def register_handler(self, handler: Handler) -> None:
        """Register a handler for a command type."""
        self._handlers[handler.command_type] = handler

    def register_projection(self, projection: Projection) -> None:
        """Register a projection to receive events."""
        self._projections.append(projection)

    # -------------------------------------------------------------------------
    # Core dispatch
    # -------------------------------------------------------------------------

    async def dispatch(
        self, command: Command, context: ExecutionContext | None = None
    ) -> list[Event]:
        """Dispatch a command through the full CQRS pipeline.

        Raises:
            UnauthorizedError: If PEEL denies the action.
            HandlerNotFoundError: If no handler registered for command type.
            CommandValidationError: If command validation fails.
            HandlerExecutionError: If handler fails.
        """
        if self.peel and context:
            action = command.action_name or command.type
            resource = command.target_resource_grn or f"grn://{command.organization_id}/*"
            await self.peel.authorize(context, action, resource)

        handler = self._handlers.get(command.type)
        if not handler:
            raise HandlerNotFoundError(
                f"No handler registered for command type '{command.type}'"
            )

        events = await handler.handle(command)
        self.event_store.append_many(events)

        for event in events:
            await self._notify_projections(event)
            await self.publish(event)  # Push to real-time listeners

        return events

    async def replay_events(self, events: list[Event]) -> None:
        """Replay events to projections only (does NOT push to live listeners)."""
        for projection in self._projections:
            await projection.reset()

        for event in events:
            await self._notify_projections(event)
            # Intentionally NOT calling publish() here
            # Replays rebuild state, they should not stream to live clients

    # -------------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------------

    async def _notify_projections(self, event: Event) -> None:
        """Notify registered projections of an event."""
        for projection in self._projections:
            if event.type in projection.event_types:
                await projection.handle_event(event)