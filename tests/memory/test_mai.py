import pytest
from datetime import datetime, timezone
from uuid import uuid4

from gabriel.memory.providers.local import LocalMemoryProvider
from gabriel.memory.client import ScopedMemoryClient
from gabriel.memory.models import MemoryLayer
from gabriel.runtime.context import ExecutionContext
from gabriel.identity.principal import Principal
from gabriel.identity.principal_id import PrincipalID
from gabriel.identity.models import PrincipalType, PrincipalStatus


@pytest.fixture
def mock_context() -> ExecutionContext:
    principal = Principal(
        id=PrincipalID(
            org_id="org-123",
            principal_type="agent",
            principal_identifier="assistant",
        ),
        organization_id="org-123",
        principal_type=PrincipalType.AGENT,
        display_name="Assistant",
        status=PrincipalStatus.ACTIVE,
    )

    return ExecutionContext(
        execution_id=uuid4(),
        principal=principal,
        organization="org-123",
        correlation_id=uuid4(),
        causation_id=None,
        session_id=None,
        resource=None,
        started_at=datetime.now(timezone.utc),
        capabilities=frozenset(),
        metadata={},
    )

@pytest.mark.asyncio
async def test_scoped_memory_usage(mock_context):
    provider = LocalMemoryProvider()
    client = ScopedMemoryClient(mock_context, provider)
    
    await client.write("User likes coffee", layer=MemoryLayer.LONG_TERM)
    
    memories = await client.read(layer=MemoryLayer.LONG_TERM)
    assert len(memories) == 1
    assert memories[0].content == "User likes coffee"
    # Ensure metadata was injected
    assert "org" in memories[0].metadata
    assert memories[0].metadata["org"] == "org-123"
    assert memories[0].metadata["principal"].startswith("principal://")


@pytest.mark.asyncio
async def test_forget_memory(mock_context):
    provider = LocalMemoryProvider()
    client = ScopedMemoryClient(mock_context, provider)

    memory_id = await client.write("Temporary fact", layer=MemoryLayer.SHORT_TERM)
    memories_before = await client.read(layer=MemoryLayer.SHORT_TERM)
    assert len(memories_before) == 1

    await client.forget(memory_id)
    memories_after = await client.read(layer=MemoryLayer.SHORT_TERM)
    assert memories_after == []