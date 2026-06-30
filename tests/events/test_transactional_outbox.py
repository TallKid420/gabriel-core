"""Tests for transactional outbox pattern (ADR-017): event emission atomicity."""
import pytest
from gabriel.organization.models import Organization
from gabriel.organization.repository import OrganizationRepository
from gabriel.organization.service import OrganizationService
from gabriel.identity.models import PrincipalType, Capability
from gabriel.identity.principal import Principal
from gabriel.identity.repository import PrincipalRepository
from gabriel.identity.service import PrincipalService
from gabriel.events.repository import EventRepository
from gabriel.events.orm import EventORM
from gabriel.resource.bootstrap import register_core_resource_types
from gabriel.resource.registry import ResourceRegistry


@pytest.mark.asyncio
async def test_org_creation_emits_resource_created_event(db_session):
    """Test that creating an organization emits exactly one resource_created event."""
    register_core_resource_types()
    
    org_repo = OrganizationRepository(db_session)
    event_repo = EventRepository(db_session)
    org_service = OrganizationService(org_repo, event_repo)
    
    # Create org
    org = await org_service.register_organization("Acme Corp", "admin")
    
    # Query events for this org
    events = await event_repo.events_for_organization(org.org_id)
    
    # Should have exactly one resource_created event
    assert len(events) == 1
    
    event = events[0]
    assert event.type == "resource_created"
    assert event.organization_id == org.org_id
    assert event.principal_id == "admin"
    assert event.resource_grn == str(org.grn)
    
    # Verify payload contains resource info
    assert event.payload["resource_type"] == "organization"
    assert event.payload["display_name"] == "Acme Corp"


@pytest.mark.asyncio
async def test_principal_creation_emits_resource_created_event(db_session):
    """Test that creating a principal emits exactly one resource_created event."""
    register_core_resource_types()
    
    
    principal_repo = PrincipalRepository(db_session)
    event_repo = EventRepository(db_session)
    principal_service = PrincipalService(principal_repo, event_repo=event_repo)
    
    # Create principal
    principal = await principal_service.register_principal(
        org_id="acme",
        principal_type=PrincipalType.USER,
        principal_identifier="alice",
        display_name="Alice Smith",
        capabilities=[Capability.READ_RESOURCE],
    )
    
    # Query events for this org
    events = await event_repo.events_for_organization("acme")
    
    # Should have exactly one resource_created event
    assert len(events) == 1
    
    event = events[0]
    assert event.type == "resource_created"
    assert event.organization_id == "acme"
    assert event.resource_grn == principal.resource_grn
    assert event.principal_id == "system"  # Default created_by value
    
    # Verify payload
    assert event.payload["resource_type"] == "principal"
    assert event.payload["display_name"] == "Alice Smith"


@pytest.mark.asyncio
async def test_event_references_correct_grn_and_principal(db_session):
    """Test that emitted events reference the correct resource GRN and principal."""
    register_core_resource_types()
    
    org_repo = OrganizationRepository(db_session)
    event_repo = EventRepository(db_session)
    org_service = OrganizationService(org_repo, event_repo)
    
    # Create org with specific principal
    principal_id = "principal://admin-org/user/admin"
    org = await org_service.register_organization("TestCorp", principal_id)
    
    # Get event
    events = await event_repo.events_for_organization(org.org_id)
    assert len(events) == 1
    
    event = events[0]
    
    # Verify GRN format: grn:<org>:<resource_type>/<resource_id>:<version>
    grn_str = event.resource_grn
    assert grn_str.startswith("grn:")
    assert org.org_id in grn_str
    assert "organization" in grn_str
    assert ":1" in grn_str  # version
    
    # Verify principal matches
    assert event.principal_id == principal_id


@pytest.mark.asyncio
async def test_multiple_creates_emit_multiple_events(db_session):
    """Test that multiple resource creates emit corresponding events."""
    register_core_resource_types()
    
    
    org_repo = OrganizationRepository(db_session)
    principal_repo = PrincipalRepository(db_session)
    event_repo = EventRepository(db_session)
    
    org_service = OrganizationService(org_repo, event_repo)
    principal_service = PrincipalService(principal_repo, event_repo=event_repo)
    
    # Create org
    org = await org_service.register_organization("MultiTest", "admin")
    
    # Create 3 principals in that org
    for i in range(3):
        await principal_service.register_principal(
            org_id=org.org_id,
            principal_type=PrincipalType.USER,
            principal_identifier=f"user-{i}",
            display_name=f"User {i}",
            capabilities=[],
        )
    
    # Query events: should have 1 org + 3 principal events = 4 total
    events = await event_repo.events_for_organization(org.org_id)
    assert len(events) == 4
    
    # Verify types
    event_types = [e.type for e in events]
    assert event_types.count("resource_created") == 4


@pytest.mark.asyncio
async def test_events_by_resource_grn(db_session):
    """Test that we can efficiently query events by resource GRN."""
    register_core_resource_types()
    
    
    org_repo = OrganizationRepository(db_session)
    principal_repo = PrincipalRepository(db_session)
    event_repo = EventRepository(db_session)
    
    org_service = OrganizationService(org_repo, event_repo)
    principal_service = PrincipalService(principal_repo, event_repo=event_repo)
    
    # Create org
    org = await org_service.register_organization("EventTest", "admin")
    
    # Create a specific principal
    principal = await principal_service.register_principal(
        org_id=org.org_id,
        principal_type=PrincipalType.USER,
        principal_identifier="alice",
        display_name="Alice",
        capabilities=[],
    )
    
    # Query events for the principal resource
    events = await event_repo.events_for_resource(principal.resource_grn)
    
    assert len(events) == 1
    assert events[0].resource_grn == principal.resource_grn
    assert events[0].type == "resource_created"


@pytest.mark.asyncio
async def test_event_has_principal_id_field(db_session):
    """Test that events correctly capture the acting principal."""
    register_core_resource_types()
    
    org_repo = OrganizationRepository(db_session)
    event_repo = EventRepository(db_session)
    org_service = OrganizationService(org_repo, event_repo)
    
    acting_principal = "principal://system/user/deployer"
    org = await org_service.register_organization("PrincipalTest", acting_principal)
    
    events = await event_repo.events_for_organization(org.org_id)
    assert len(events) == 1
    
    # Verify principal_id captures the acting principal
    assert events[0].principal_id == acting_principal


@pytest.mark.asyncio
async def test_event_payload_contains_resource_info(db_session):
    """Test that event payload contains resource type and key info."""
    register_core_resource_types()
    
    org_repo = OrganizationRepository(db_session)
    event_repo = EventRepository(db_session)
    org_service = OrganizationService(org_repo, event_repo)
    
    org = await org_service.register_organization("PayloadTest", "admin")
    
    events = await event_repo.events_for_organization(org.org_id)
    event = events[0]
    
    # Payload should contain resource_type and identifying info
    assert "resource_type" in event.payload
    assert event.payload["resource_type"] == "organization"
    assert "display_name" in event.payload
    assert event.payload["display_name"] == "PayloadTest"


@pytest.mark.asyncio
async def test_event_grn_matches_resource_grn(db_session):
    """Test that event.resource_grn exactly matches the created resource's GRN."""
    register_core_resource_types()
    
    
    org_repo = OrganizationRepository(db_session)
    principal_repo = PrincipalRepository(db_session)
    event_repo = EventRepository(db_session)
    
    org_service = OrganizationService(org_repo, event_repo)
    principal_service = PrincipalService(principal_repo, event_repo=event_repo)
    
    # Create principal
    principal = await principal_service.register_principal(
        org_id="test-org",
        principal_type=PrincipalType.AGENT,
        principal_identifier="bot-01",
        display_name="Test Bot",
        capabilities=[],
    )
    
    # Get event
    events = await event_repo.events_for_organization("test-org")
    event = events[0]
    
    # Event GRN should exactly match principal's resource_grn
    assert event.resource_grn == principal.resource_grn
