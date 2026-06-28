"""Tests for ExecutionContext."""
import pytest
import json
from uuid import uuid4
from datetime import datetime, timezone

from gabriel.runtime.context import ExecutionContext
from gabriel.runtime.capabilities import Capability as RuntimeCapability
from gabriel.identity.principal import Principal
from gabriel.identity.models import PrincipalType


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TestExecutionContextImmutability:
    """Test that ExecutionContext is frozen and immutable."""

    def test_context_is_frozen(self, execution_context: ExecutionContext):
        """Frozen dataclass cannot be modified."""
        with pytest.raises(AttributeError):
            execution_context.organization = "other-org"

    def test_context_cannot_modify_metadata(self, execution_context: ExecutionContext):
        """Metadata dict contents are immutable by reference (frozen dataclass property)."""
        # Note: Frozen dataclass prevents assignment, but doesn't prevent
        # modification of mutable dict contents. This is a limitation of Python.
        # The field is part of an immutable object though.
        with pytest.raises(AttributeError):
            # Can't reassign the metadata field itself
            execution_context.metadata = {"new": "value"}

    def test_context_cannot_modify_capabilities(self, execution_context: ExecutionContext):
        """Capabilities frozenset is immutable."""
        with pytest.raises(AttributeError):
            execution_context.capabilities.add("new_capability")


class TestExecutionContextHashability:
    """Test that ExecutionContext is hashable."""

    def test_context_is_hashable(self, execution_context: ExecutionContext):
        """ExecutionContext can be used as dict key or in set."""
        context_set = {execution_context}
        assert execution_context in context_set

    def test_same_context_same_hash(self, principal: Principal, org_id: str):
        """Same context produces same hash."""
        ctx1 = ExecutionContext(
            execution_id=uuid4(),
            principal=principal,
            organization=org_id,
            correlation_id=uuid4(),
            causation_id=None,
            session_id=None,
            resource=None,
            started_at=utcnow(),
            capabilities=frozenset([RuntimeCapability.READ_MEMORY.value]),
            metadata={},
        )
        ctx2 = ExecutionContext(
            execution_id=ctx1.execution_id,
            principal=principal,
            organization=org_id,
            correlation_id=ctx1.correlation_id,
            causation_id=None,
            session_id=None,
            resource=None,
            started_at=ctx1.started_at,
            capabilities=frozenset([RuntimeCapability.READ_MEMORY.value]),
            metadata={},
        )
        assert hash(ctx1) == hash(ctx2)

    def test_context_in_dict(self, execution_context: ExecutionContext):
        """ExecutionContext can be used as dict key."""
        context_dict = {execution_context: "test_value"}
        assert context_dict[execution_context] == "test_value"


class TestExecutionContextEquality:
    """Test ExecutionContext equality."""

    def test_same_id_equal(self, principal: Principal, org_id: str):
        """Contexts with same execution_id and key fields are equal."""
        exec_id = uuid4()
        corr_id = uuid4()
        ctx1 = ExecutionContext(
            execution_id=exec_id,
            principal=principal,
            organization=org_id,
            correlation_id=corr_id,
            causation_id=None,
            session_id=None,
            resource=None,
            started_at=utcnow(),
            capabilities=frozenset(),
            metadata={},
        )
        ctx2 = ExecutionContext(
            execution_id=exec_id,
            principal=principal,
            organization=org_id,
            correlation_id=corr_id,
            causation_id=None,
            session_id=None,
            resource=None,
            started_at=utcnow(),
            capabilities=frozenset(),
            metadata={},
        )
        # Contexts with same execution_id and organization are equal
        assert ctx1 == ctx2

    def test_different_execution_id_not_equal(
        self, principal: Principal, org_id: str
    ):
        """Contexts with different execution_ids are not equal."""
        corr_id = uuid4()
        ctx1 = ExecutionContext(
            execution_id=uuid4(),
            principal=principal,
            organization=org_id,
            correlation_id=corr_id,
            causation_id=None,
            session_id=None,
            resource=None,
            started_at=utcnow(),
            capabilities=frozenset(),
            metadata={},
        )
        ctx2 = ExecutionContext(
            execution_id=uuid4(),
            principal=principal,
            organization=org_id,
            correlation_id=corr_id,
            causation_id=None,
            session_id=None,
            resource=None,
            started_at=utcnow(),
            capabilities=frozenset(),
            metadata={},
        )
        assert ctx1 != ctx2

    def test_not_equal_to_other_types(self, execution_context: ExecutionContext):
        """ExecutionContext is not equal to other types."""
        assert execution_context != "string"
        assert execution_context != 42
        assert execution_context != None


class TestExecutionContextSerialization:
    """Test ExecutionContext serialization."""

    def test_to_dict(self, execution_context: ExecutionContext):
        """to_dict produces a serializable dict."""
        d = execution_context.to_dict()
        assert "execution_id" in d
        assert "principal_id" in d
        assert "organization" in d
        assert "correlation_id" in d
        assert all(isinstance(v, (str, int, list, dict, type(None))) for v in d.values())

    def test_to_json(self, execution_context: ExecutionContext):
        """to_json produces valid JSON string."""
        json_str = execution_context.to_json()
        parsed = json.loads(json_str)
        assert "execution_id" in parsed
        assert "organization" in parsed

    def test_serialized_dict_preserves_info(self, execution_context: ExecutionContext):
        """Serialized dict preserves key information."""
        d = execution_context.to_dict()
        assert d["execution_id"] == str(execution_context.execution_id)
        assert d["organization"] == execution_context.organization
        assert d["correlation_id"] == str(execution_context.correlation_id)


class TestExecutionContextCapabilities:
    """Test capability checking."""

    def test_has_capability_true(self, execution_context: ExecutionContext):
        """has_capability returns True when present."""
        # execution_context has READ_MEMORY from fixture
        assert execution_context.has_capability("read_memory")

    def test_has_capability_false(self, execution_context: ExecutionContext):
        """has_capability returns False when absent."""
        assert not execution_context.has_capability("nonexistent_capability")

    def test_has_all_principal_capabilities(self, principal: Principal, org_id: str):
        """ExecutionContext has all principal's capabilities."""
        ctx = ExecutionContext(
            execution_id=uuid4(),
            principal=principal,
            organization=org_id,
            correlation_id=uuid4(),
            causation_id=None,
            session_id=None,
            resource=None,
            started_at=utcnow(),
            capabilities=frozenset([cap.value for cap in principal.capabilities]),
            metadata={},
        )
        for cap in principal.capabilities:
            assert ctx.has_capability(cap.value)

    def test_limited_principal_has_limited_capabilities(
        self, limited_principal: Principal, org_id: str
    ):
        """Limited principal has only specified capabilities."""
        ctx = ExecutionContext(
            execution_id=uuid4(),
            principal=limited_principal,
            organization=org_id,
            correlation_id=uuid4(),
            causation_id=None,
            session_id=None,
            resource=None,
            started_at=utcnow(),
            capabilities=frozenset(
                [RuntimeCapability.READ_MEMORY.value, RuntimeCapability.INVOKE_TOOL.value]
            ),
            metadata={},
        )
        assert ctx.has_capability("read_memory")
        assert ctx.has_capability("invoke_tool")
        assert not ctx.has_capability("delete_resource")
        assert not ctx.has_capability("create_resource")


class TestExecutionContextStringRepresentation:
    """Test string representation."""

    def test_str_representation(self, execution_context: ExecutionContext):
        """__str__ returns readable string."""
        s = str(execution_context)
        assert "ExecutionContext" in s
        assert "id=" in s
        assert "org=" in s

    def test_repr_representation(self, execution_context: ExecutionContext):
        """__repr__ returns informative repr."""
        r = repr(execution_context)
        assert "ExecutionContext" in r
        assert "execution_id=" in r
