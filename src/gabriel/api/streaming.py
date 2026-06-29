import asyncio
from typing import AsyncGenerator
from gabriel.events.dispatcher import Dispatcher
from gabriel.events.event import Event

class EventStreamer:
    def __init__(self, dispatcher: Dispatcher):
        self.dispatcher = dispatcher

    async def stream_events(self, organization_id: str) -> AsyncGenerator[str, None]:
        """
        Listens to the internal event bus and yields formatted SSE messages.
        Filters events by organization for security.
        """
        queue = self.dispatcher.subscribe()
        try:
            while True:
                event : Event = await queue.get()
                if event.organization_id == organization_id:
                    # Format as Server-Sent Event (SSE)
                    yield f"data: {event.model_dump_json()}\n\n"
        finally:
            self.dispatcher.unsubscribe(queue)