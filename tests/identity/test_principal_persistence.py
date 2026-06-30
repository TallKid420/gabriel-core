"""Tests for Principal persistence layer (repository pattern)."""
import pytest
from gabriel.identity.principal import Principal
from gabriel.identity.principal_id import PrincipalID
from gabriel.identity.models import PrincipalType, Capability
from gabriel.identity.repository import PrincipalRepository
from gabriel.identity.service import PrincipalService
from gabriel.resource.bootstrap import register_core_resource_types


@pytest.mark.asyncio
async def test_create_and_retrieve_principal(db_session):
    """Test that Principals are created as domain objects and properly persisted."""
    # Setup
    register_core_resource_types()
    
    
    repo = PrincipalRepository(db_session)
    service = PrincipalService(repo)
    
    # Create principal
    principal = await service.register_principal(
        org_id="acme",
        principal_type=PrincipalType.USER,
        principal_identifier="alice",
        display_name="Alice Smith",
        capabilities=[Capability.READ_RESOURCE, Capability.WRITE_RESOURCE],
    )
    
    # Verify domain object
    assert isinstance(principal, Principal)
    assert principal.display_name == "Alice Smith"
    assert principal.status == "active"  # Default
    assert Capability.READ_RESOURCE in principal.capabilities
    assert Capability.WRITE_RESOURCE in principal.capabilities
    assert str(principal.id).startswith("principal://")
    
    # Verify persisted resource_grn (mirror link)
    assert principal.resource_grn is not None
    assert str(principal.resource_grn).startswith("grn:")
    assert "acme" in str(principal.resource_grn)
    
    # Retrieve
    retrieved = await service.get_principal(str(principal.id))
    assert isinstance(retrieved, Principal)
    assert retrieved.display_name == "Alice Smith"
    assert retrieved.id == principal.id
    assert retrieved.status == "active"


@pytest.mark.asyncio
async def test_principal_capability_round_trip(db_session):
    """Test that capabilities survive JSON serialization/deserialization."""
    register_core_resource_types()
    
    
    repo = PrincipalRepository(db_session)
    service = PrincipalService(repo)
    
    # Create with mixed capabilities
    capabilities = [
        Capability.READ_RESOURCE,
        Capability.WRITE_RESOURCE,
        Capability.EXECUTE_WORKFLOW,
        Capability.MANAGE_PRINCIPALS,
    ]
    
    principal = await service.register_principal(
        org_id="acme",
        principal_type=PrincipalType.AGENT,
        principal_identifier="bot-01",
        display_name="Bot One",
        capabilities=capabilities,
    )
    
    # Store original
    original_caps = set(principal.capabilities)
    
    # Retrieve and verify
    retrieved = await service.get_principal(str(principal.id))
    retrieved_caps = set(retrieved.capabilities)
    
    assert original_caps == retrieved_caps
    assert len(retrieved.capabilities) == 4


@pytest.mark.asyncio
async def test_principal_status_defaults_to_active(db_session):
    """Test that principal status defaults to 'active'."""
    register_core_resource_types()
    
    
    repo = PrincipalRepository(db_session)
    service = PrincipalService(repo)
    
    principal = await service.register_principal(
        org_id="acme",
        principal_type=PrincipalType.USER,
        principal_identifier="bob",
        display_name="Bob Jones",
        capabilities=[],
    )
    
    # Status should default to active
    assert principal.status == "active"
    
    # Verify persisted default
    retrieved = await service.get_principal(str(principal.id))
    assert retrieved.status == "active"


@pytest.mark.asyncio
async def test_list_principals_for_organization(db_session):
    """Test listing all principals in an organization."""
    register_core_resource_types()
    
    
    repo = PrincipalRepository(db_session)
    service = PrincipalService(repo)
    
    org_id = "acme"
    
    # Create multiple principals in same org
    principal1 = await service.register_principal(
        org_id=org_id,
        principal_type=PrincipalType.USER,
        principal_identifier="alice",
        display_name="Alice",
        capabilities=[],
    )
    
    principal2 = await service.register_principal(
        org_id=org_id,
        principal_type=PrincipalType.AGENT,
        principal_identifier="bot-01",
        display_name="Bot One",
        capabilities=[],
    )
    
    # List
    principals = await service.list_principals_for_org(org_id)
    
    assert len(principals) == 2
    assert all(isinstance(p, Principal) for p in principals)
    assert {p.display_name for p in principals} == {"Alice", "Bot One"}


@pytest.mark.asyncio
async def test_principal_principal_id_format(db_session):
    """Test that PrincipalID follows expected format."""
    register_core_resource_types()
    
    
    repo = PrincipalRepository(db_session)
    service = PrincipalService(repo)
    
    principal = await service.register_principal(
        org_id="acme",
        principal_type=PrincipalType.USER,
        principal_identifier="alice",
        display_name="Alice",
        capabilities=[],
    )
    
    # Verify format: principal://org/type/identifier
    pid_str = str(principal.id)
    assert pid_str.startswith("principal://")
    assert "acme" in pid_str
    assert "user" in pid_str
    assert "alice" in pid_str
    
    # Verify it can be parsed back
    parsed = PrincipalID.parse(pid_str)
    assert parsed.org_id == "acme"
    assert parsed.principal_type == PrincipalType.USER
    assert parsed.principal_identifier == "alice"
