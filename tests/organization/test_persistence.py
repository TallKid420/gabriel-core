import pytest
from gabriel.organization.service import OrganizationService
from gabriel.organization.repository import OrganizationRepository
from gabriel.organization.models import Organization
from gabriel.resource.exceptions import DuplicateResourceError
from gabriel.events.repository import EventRepository
from gabriel.resource.bootstrap import register_core_resource_types


@pytest.mark.asyncio
async def test_create_and_retrieve_organization(db_session):
    """Test that Organizations are returned as domain objects, not ORM."""
    repo = OrganizationRepository(db_session)
    service = OrganizationService(repo)

    # Create
    org = await service.register_organization("Cyberdyne Systems", "admin")
    
    # Verify it's a domain object, not ORM
    assert isinstance(org, Organization)
    assert org.display_name == "Cyberdyne Systems"
    assert org.created_by == "admin"
    assert str(org.grn).startswith("grn:")

    # Retrieve
    retrieved = await service.get_organization(str(org.grn))
    assert isinstance(retrieved, Organization)
    assert retrieved.display_name == "Cyberdyne Systems"
    assert retrieved.grn == org.grn


@pytest.mark.asyncio
async def test_duplicate_organization_fails(db_session):
    """Test that creating duplicate organizations is rejected."""
    repo = OrganizationRepository(db_session)
    service = OrganizationService(repo)

    # Create first organization
    await service.register_organization("Acme Corp", "admin")

    # Attempt duplicate — should fail
    with pytest.raises(DuplicateResourceError):
        await service.register_organization("Acme Corp", "admin")


@pytest.mark.asyncio
async def test_list_organizations(db_session):
    """Test listing organizations as domain objects."""
    repo = OrganizationRepository(db_session)
    service = OrganizationService(repo)

    # Create a few
    org1 = await service.register_organization("Alpha Corp", "admin")
    org2 = await service.register_organization("Beta Inc", "admin")

    # List all
    all_orgs = await service.list_organizations()
    assert len(all_orgs) == 2
    assert all(isinstance(org, Organization) for org in all_orgs)
    assert {org.display_name for org in all_orgs} == {"Alpha Corp", "Beta Inc"}


@pytest.mark.asyncio
async def test_organization_with_event_emission(db_session):
    """Test that creating an organization with event repo emits resource_created event."""
    register_core_resource_types()
    
    org_repo = OrganizationRepository(db_session)
    event_repo = EventRepository(db_session)
    service = OrganizationService(org_repo, event_repo)

    # Create org with event emission
    org = await service.register_organization("EventOrg", "admin")
    
    # Verify org created
    assert isinstance(org, Organization)
    assert org.display_name == "EventOrg"
    
    # Verify event was emitted
    events = await event_repo.events_for_organization(org.org_id)
    assert len(events) == 1
    
    event = events[0]
    assert event.type == "resource_created"
    assert event.organization_id == org.org_id
    assert event.principal_id == "admin"
    assert event.resource_grn == str(org.grn)
    assert event.payload["resource_type"] == "organization"
    assert event.payload["display_name"] == "EventOrg"


@pytest.mark.asyncio
async def test_organization_grn_format(db_session):
    """Test that Organization GRN follows expected format: grn:<org>:<resource_type>/<id>:<version>."""
    repo = OrganizationRepository(db_session)
    service = OrganizationService(repo)

    org = await service.register_organization("GRNFormatTest", "admin")
    
    grn_str = str(org.grn)
    
    # Verify format
    assert grn_str.startswith("grn:")
    assert org.org_id in grn_str
    assert "organization" in grn_str
    assert ":1" in grn_str  # version defaults to 1
    
    # Parse format: grn:<org>:<type>/<id>:<version>
    parts = grn_str.split(":")
    assert len(parts) >= 4  # grn, org_id, type/id, version
    assert parts[0] == "grn"
    assert parts[1] == org.org_id
