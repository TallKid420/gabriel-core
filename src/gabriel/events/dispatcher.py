# src/gabriel/events/dispatcher.py

"""Dispatcher: Routes commands to handlers, stores events, updates projections."""

import asyncio

from gabriel.events.command import Command
from gabriel.events.event import Event
from gabriel.events.event_store import EventStore
from gabriel.events.exceptions import HandlerNotFoundError
from gabriel.events.handler import Handler
from gabriel.events.projection import Projection
from gabriel.runtime.context import ExecutionContext


class Dispatcher:
    """Orchestrates the CQRS flow with optional PEEL authorization.

    Two event tracks exist and must not be mixed:

    Track 1 — Platform Events (Causal):
        dispatch(command) → [PEEL] → Handler → Events → EventStore → Projections → Listeners
        Use for any operation that changes Resource state. These events are permanent.

    Track 2 — Telemetry Events (Ephemeral):
        publish(event) → Listeners only
        Use for live UI signals: node progress, token usage, heartbeats, spinners.
        These events are NOT persisted and do NOT update projections.
        If no listener is subscribed at the moment of publish(), the event is silently dropped.

    Rule: If an event needs to update a Projection, it MUST go through dispatch().
          The only way to change read-model state is to record a permanent fact first.
    """

    def __init__(self, event_store: EventStore, peel=None) -> None:
        self.event_store = event_store
        self.peel = peel
        self._handlers: dict[str, Handler] = {}
        self._projections: list[Projection] = []
        self._listeners: list[asyncio.Queue] = []

    # -------------------------------------------------------------------------
    # Track 2 — Telemetry / Ephemeral streaming
    # -------------------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        """Register a new real-time listener queue.

        The caller MUST call unsubscribe() when done. Failing to do so
        will cause the listener list to grow unbounded over time.

        Returns:
            asyncio.Queue: The queue to read telemetry events from.
        """
        queue: asyncio.Queue = asyncio.Queue()
        self._listeners.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Remove a listener queue. Safe to call if the queue is not registered."""
        if queue in self._listeners:
            self._listeners.remove(queue)

    async def publish(self, event: Event) -> None:
        """Publish a telemetry event to all live listeners.

        This is Track 2 — ephemeral, streaming-only.

        - NOT persisted to the EventStore.
        - Does NOT notify Projections.
        - If no listener is subscribed, the event is silently dropped.

        Use this for live UI signals only:
            - "Agent is thinking..."
            - "Node completed."
            - "LLM usage: 50 tokens."

        If the event needs to change Resource state or update a Projection,
        dispatch a Command instead. publish() must never be used as a
        shortcut for state mutation.
        """
        for queue in self._listeners:
            await queue.put(event)

    # -------------------------------------------------------------------------
    # Registration
    # -------------------------------------------------------------------------

    def register_handler(self, handler: Handler) -> None:
        """Register a command handler. One handler per command type."""
        self._handlers[handler.command_type] = handler

    def register_projection(self, projection: Projection) -> None:
        """Register a projection to receive events from dispatch()."""
        self._projections.append(projection)

    # -------------------------------------------------------------------------
    # Track 1 — Platform Events / Full CQRS pipeline
    # -------------------------------------------------------------------------

    async def dispatch(
        self, command: Command, context: ExecutionContext | None = None
    ) -> list[Event]:
        """Dispatch a command through the full CQRS pipeline.

        This is Track 1 — causal, persistent, projection-aware.

        Flow:
            1. [PEEL] Authorize action (if PEEL is configured)
            2. Resolve handler for command.type
            3. Execute handler → produce events
            4. Persist events to EventStore
            5. Notify registered Projections
            6. Stream events to live listeners (Track 2 queues)

        Note: dispatch() also streams to listeners so that causal events
        are visible in the live UI alongside telemetry events. The difference
        is that causal events are persisted first — they are never ephemeral.

        Raises:
            UnauthorizedError: If PEEL denies the action.
            HandlerNotFoundError: If no handler is registered for command.type.
            CommandValidationError: If command validation fails.
            HandlerExecutionError: If the handler raises.
        """
        if self.peel and context:
            action = command.action_name or command.type
            resource = command.target_resource_grn or f"grn:{command.organization_id}/*"
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
            for queue in self._listeners:
                await queue.put(event)

        return events

    async def replay_events(self, events: list[Event]) -> None:
        """Replay a sequence of events to rebuild Projection state.

        Does NOT stream to live listeners — replay is a state reconstruction
        operation, not a live event feed.

        Raises:
            TypeError: If a registered Projection does not implement reset().
                       All Projection subclasses must implement async reset() -> None.
        """
        for projection in self._projections:
            if not hasattr(projection, "reset") or not callable(projection.reset):
                raise TypeError(
                    f"Projection {type(projection).__name__} does not implement reset(). "
                    "All Projection subclasses must implement async reset() -> None."
                )
            await projection.reset()

        for event in events:
            await self._notify_projections(event)

    # -------------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------------

    async def _notify_projections(self, event: Event) -> None:
        for projection in self._projections:
            if event.type in projection.event_types:
                await projection.handle_event(event)