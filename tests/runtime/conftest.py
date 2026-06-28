"""Fixtures for runtime tests."""
import pytest
from uuid import UUID, uuid4
from datetime import datetime, timezone
import pytest_asyncio

from gabriel.identity.principal import Principal
from gabriel.identity.principal_id import PrincipalID
from gabriel.identity.models import PrincipalType, Capability as IdentityCapability
from gabriel.resource.grn import GRN
from gabriel.runtime.context import ExecutionContext
from gabriel.runtime.capabilities import Capability as RuntimeCapability
from gabriel.runtime.execution import ExecutionContextBuilder, Execution, ExecutionState
from gabriel.events.event import Event


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def org_id() -> str:
    return "test-org"


@pytest.fixture
def principal(org_id: str) -> Principal:
    """Create a test principal with all capabilities."""
    return Principal(
        id=PrincipalID(
            org_id=org_id,
            principal_type="service_account",
            principal_identifier="test-service",
        ),
        organization_id=org_id,
        principal_type=PrincipalType.SERVICE_ACCOUNT,
        display_name="Test Service",
        capabilities={
            IdentityCapability.AUTHENTICATE,
            IdentityCapability.READ_ORGANIZATION,
            IdentityCapability.EXECUTE_WORKFLOW,
            IdentityCapability.CALL_TOOL,
            IdentityCapability.WRITE_RESOURCE,
        },
    )


@pytest.fixture
def limited_principal(org_id: str) -> Principal:
    """Create a principal with limited capabilities."""
    return Principal(
        id=PrincipalID(
            org_id=org_id,
            principal_type="user",
            principal_identifier="test-user",
        ),
        organization_id=org_id,
        principal_type=PrincipalType.USER,
        display_name="Test User",
        capabilities={
            IdentityCapability.READ_ORGANIZATION,
            IdentityCapability.CALL_TOOL,
        },
    )


@pytest.fixture
def execution_context(principal: Principal, org_id: str) -> ExecutionContext:
    """Create a test execution context."""
    return ExecutionContext(
        execution_id=uuid4(),
        principal=principal,
        organization=org_id,
        correlation_id=uuid4(),
        causation_id=None,
        session_id=None,
        resource=None,
        started_at=utcnow(),
        capabilities=frozenset(
            [RuntimeCapability.READ_MEMORY.value, RuntimeCapability.WRITE_MEMORY.value]
        ),
        metadata={"test": "true"},
    )


@pytest.fixture
def execution(execution_context: ExecutionContext) -> Execution:
    """Create a test execution."""
    return Execution(
        context=execution_context,
        state=ExecutionState.PENDING,
        started_at=utcnow(),
    )


@pytest.fixture
def test_event(org_id: str, principal: Principal) -> Event:
    """Create a test event."""
    return Event(
        id=str(uuid4()),
        type="test.event",
        occurred_at=utcnow(),
        principal_id=str(principal.id),
        organization_id=org_id,
        resource_grn=None,
        correlation_id=str(uuid4()),
        causation_id=None,
        payload={},
        metadata={},
    )


@pytest.fixture
def context_builder() -> ExecutionContextBuilder:
    """Create an execution context builder."""
    return ExecutionContextBuilder()


@pytest.fixture
def scoped_client(execution_context: ExecutionContext):
    """Create a scoped client."""
    from gabriel.runtime.scope import ScopedClient
    return ScopedClient(execution_context)
