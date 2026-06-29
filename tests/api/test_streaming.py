from __future__ import annotations

import asyncio
import pytest
from gabriel.events.event import Event
from gabriel.api.dependencies import get_event_streamer


class _OneShotEventStreamer:
    async def stream_events(self, organization_id: str):
        yield ": connected\n\n"


@pytest.mark.asyncio
async def test_event_stream_connectivity(client, auth_headers):
    """Test that the stream endpoint connects and returns SSE content-type."""
    # TestClient doesn't support true async streaming, so we just verify
    # the endpoint exists and returns the correct media type.
    # Full streaming integration requires a live ASGI server (e.g. pytest-anyio + httpx).
    client.app.dependency_overrides[get_event_streamer] = lambda: _OneShotEventStreamer()
    try:
        with client.stream("GET", "/events/stream", headers=auth_headers) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
    finally:
        client.app.dependency_overrides.pop(get_event_streamer, None)


@pytest.mark.asyncio
async def test_dispatcher_publish_reaches_subscriber():
    """Test that publish() pushes events to subscribed queues."""
    from gabriel.events.event_store import EventStore
    from gabriel.events.dispatcher import Dispatcher

    store = EventStore()
    dispatcher = Dispatcher(event_store=store)

    queue = dispatcher.subscribe()

    event = Event(
        type="test.event",
        principal_id="principal://org_123/system/test",
        organization_id="org_123",
        payload={"msg": "hello"},
    )

    await dispatcher.publish(event)

    received = queue.get_nowait()
    assert received.type == "test.event"
    assert received.principal_id == "principal://org_123/system/test"
    assert received.organization_id == "org_123"

    dispatcher.unsubscribe(queue)
    assert queue not in dispatcher._listeners