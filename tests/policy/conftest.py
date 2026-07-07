"""Fixtures for policy tests."""
import pytest
import pytest_asyncio
from uuid import uuid4
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from gabriel.database.base import Base

# Import ORM models so Base.metadata includes required tables.
import gabriel.organization.orm  # noqa: F401
import gabriel.identity.orm  # noqa: F401
import gabriel.events.orm  # noqa: F401
import gabriel.policy.orm  # noqa: F401

from gabriel.policy.models import Policy, PolicyStatement, Effect, ResourceType
from gabriel.policy.engine import PolicyEngine, EvaluationRequest
from gabriel.resource.grn import GRN
from gabriel.identity.principal_id import PrincipalID
from gabriel.identity.principal import Principal
from gabriel.identity.models import PrincipalType, Capability as IdentityCapability
from gabriel.runtime.context import ExecutionContext
from gabriel.runtime.capabilities import Capability as RuntimeCapability
from datetime import datetime, timezone


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
def org_id() -> str:
    return "test-org"


@pytest.fixture
def principal(org_id: str) -> Principal:
    """Create a test principal."""
    return Principal(
        id=PrincipalID(
            org_id=org_id,
            principal_type="service_account",
            principal_identifier="test-service",
        ),
        organization_id=org_id,
        principal_type=PrincipalType.SERVICE_ACCOUNT,
        display_name="Test Service",
        capabilities={IdentityCapability.AUTHENTICATE},
    )


@pytest.fixture
def allow_all_statement() -> PolicyStatement:
    """Create an ALLOW * statement."""
    return PolicyStatement(
        effect=Effect.ALLOW,
        principal_match="*",
        action_match="*",
        resource_match="*",
    )


@pytest.fixture
def deny_admin_statement() -> PolicyStatement:
    """Create a DENY statement for admin actions."""
    return PolicyStatement(
        effect=Effect.DENY,
        principal_match="*",
        action_match="admin:*",
        resource_match="*",
    )


@pytest.fixture
def allow_read_statement() -> PolicyStatement:
    """Create an ALLOW statement for read actions."""
    return PolicyStatement(
        effect=Effect.ALLOW,
        principal_match="*",
        action_match="*:read",
        resource_match="*",
    )


@pytest.fixture
def allow_all_policy(org_id: str, principal: Principal, allow_all_statement: PolicyStatement) -> Policy:
    """Create a policy that allows everything."""
    grn = GRN(
        org_id=org_id,
        resource_type=ResourceType.POLICY,
        resource_id="allow-all",
    )
    return Policy.create(
        grn=grn,
        org_id=org_id,
        created_by=str(principal.id),
        statements=[allow_all_statement],
    )


@pytest.fixture
def deny_admin_policy(org_id: str, principal: Principal, deny_admin_statement: PolicyStatement) -> Policy:
    """Create a policy that denies admin actions."""
    grn = GRN(
        org_id=org_id,
        resource_type=ResourceType.POLICY,
        resource_id="deny-admin",
    )
    return Policy.create(
        grn=grn,
        org_id=org_id,
        created_by=str(principal.id),
        statements=[deny_admin_statement],
    )


@pytest.fixture
def policy_engine() -> PolicyEngine:
    """Create an empty policy engine."""
    return PolicyEngine()


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
        capabilities=frozenset([RuntimeCapability.READ_MEMORY.value]),
        metadata={},
    )
