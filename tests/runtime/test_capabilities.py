"""Tests for Capability enum and capability checking."""
import pytest

from gabriel.runtime.capabilities import Capability
from gabriel.runtime.scope import ScopedClient
from gabriel.runtime.exceptions import CapabilityError


class TestCapabilityEnum:
    """Test Capability enum."""

    def test_memory_capabilities(self):
        """Memory capabilities exist."""
        assert Capability.READ_MEMORY.value == "read_memory"
        assert Capability.WRITE_MEMORY.value == "write_memory"

    def test_tool_capabilities(self):
        """Tool capabilities exist."""
        assert Capability.INVOKE_TOOL.value == "invoke_tool"

    def test_resource_capabilities(self):
        """Resource capabilities exist."""
        assert Capability.CREATE_RESOURCE.value == "create_resource"
        assert Capability.DELETE_RESOURCE.value == "delete_resource"
        assert Capability.UPDATE_RESOURCE.value == "update_resource"

    def test_event_capabilities(self):
        """Event capabilities exist."""
        assert Capability.CREATE_EVENT.value == "create_event"

    def test_execution_capabilities(self):
        """Execution capabilities exist."""
        assert Capability.EXECUTE_AGENT.value == "execute_agent"
        assert Capability.SCHEDULE_EXECUTION.value == "schedule_execution"
        assert Capability.CANCEL_EXECUTION.value == "cancel_execution"

    def test_system_capabilities(self):
        """System capabilities exist."""
        assert Capability.VIEW_AUDIT_LOG.value == "view_audit_log"
        assert Capability.MANAGE_POLICIES.value == "manage_policies"

    def test_capabilities_are_strings(self):
        """Capabilities have string values."""
        for cap in Capability:
            assert isinstance(cap.value, str)
            assert len(cap.value) > 0

    def test_capability_values_are_lowercase(self):
        """Capability values are lowercase."""
        for cap in Capability:
            assert cap.value == cap.value.lower()


class TestScopedClientCapabilityChecking:
    """Test ScopedClient capability checking."""

    def test_has_capability_with_enum(self, scoped_client: "ScopedClient"):
        """ScopedClient.has_capability works with Capability enum."""
        # Note: scoped_client needs to be a fixture
        from gabriel.runtime.scope import ScopedClient
        from gabriel.runtime.context import ExecutionContext
        from gabriel.runtime.capabilities import Capability

        scoped_client.has_capability(Capability.READ_MEMORY)

    def test_has_capability_with_string(
        self, execution_context, org_id: str
    ):
        """ScopedClient.has_capability works with string."""
        from gabriel.runtime.scope import ScopedClient
        from gabriel.runtime.capabilities import Capability

        client = ScopedClient(execution_context)
        # execution_context has read_memory from fixture
        assert client.has_capability("read_memory")

    def test_require_capability_success(self, execution_context):
        """require_capability succeeds when capability present."""
        from gabriel.runtime.scope import ScopedClient
        from gabriel.runtime.capabilities import Capability

        client = ScopedClient(execution_context)
        client.require_capability(Capability.READ_MEMORY)  # Should not raise

    def test_require_capability_failure(self, limited_principal, org_id: str):
        """require_capability raises CapabilityError when absent."""
        from gabriel.runtime.scope import ScopedClient
        from gabriel.runtime.context import ExecutionContext
        from gabriel.runtime.capabilities import Capability
        from uuid import uuid4

        ctx = ExecutionContext(
            execution_id=uuid4(),
            principal=limited_principal,
            organization=org_id,
            correlation_id=uuid4(),
            causation_id=None,
            session_id=None,
            resource=None,
            started_at=None,
            capabilities=frozenset(
                [cap.value for cap in limited_principal.capabilities]
            ),
            metadata={},
        )
        client = ScopedClient(ctx)
        with pytest.raises(CapabilityError):
            client.require_capability(Capability.DELETE_RESOURCE)

    def test_scoped_client_principal_property(self, execution_context):
        """ScopedClient.principal property works."""
        from gabriel.runtime.scope import ScopedClient

        client = ScopedClient(execution_context)
        assert client.principal == execution_context.principal

    def test_scoped_client_organization_id_property(self, execution_context, org_id: str):
        """ScopedClient.organization_id property works."""
        from gabriel.runtime.scope import ScopedClient

        client = ScopedClient(execution_context)
        assert client.organization_id == org_id

    def test_scoped_client_execution_id_property(self, execution_context):
        """ScopedClient.execution_id property works."""
        from gabriel.runtime.scope import ScopedClient

        client = ScopedClient(execution_context)
        assert client.execution_id == execution_context.execution_id

    def test_scoped_client_metadata_access(self, execution_context):
        """ScopedClient can access metadata."""
        from gabriel.runtime.scope import ScopedClient

        client = ScopedClient(execution_context)
        assert client.metadata("test") == "true"
        assert client.metadata("nonexistent") is None

    def test_scoped_client_repr(self, execution_context):
        """ScopedClient has meaningful repr."""
        from gabriel.runtime.scope import ScopedClient

        client = ScopedClient(execution_context)
        r = repr(client)
        assert "ScopedClient" in r
