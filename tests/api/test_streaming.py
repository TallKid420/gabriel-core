import pytest
import asyncio
from httpx import AsyncClient
from gabriel.events.event import Event

@pytest.mark.asyncio
async def test_event_stream_receives_published_event(api_client: AsyncClient, dispatcher):
    # This test simulates a client connecting and then an event being dispatched
    
    async with api_client.stream("GET", "/v1/events/stream") as response:
        # Trigger an event in the background
        test_event = Event(
            type="test.event",
            organization_id="org_123",
            payload={"msg": "hello"}
        )
        
        # We manually push through dispatcher to simulate a command finish
        # In a real app, this happens when you call dispatcher.dispatch(...)
        for queue in dispatcher._listeners:
            await queue.put(test_event)
            
        # Check if the stream yielded the data
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                assert "test.event" in line
                break