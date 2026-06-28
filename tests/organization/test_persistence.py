import pytest
from gabriel.organization.service import OrganizationService
from gabriel.organization.repository import OrganizationRepository
from gabriel.organization.models import Organization
from gabriel.resource.exceptions import DuplicateResourceError


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
    assert str(org.grn).startswith("grn://")

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