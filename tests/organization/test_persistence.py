import pytest
from gabriel.organization.service import OrganizationService
from gabriel.organization.repository import OrganizationRepository

@pytest.mark.asyncio
async def test_create_and_retrieve_organization(db_session):
    repo = OrganizationRepository(db_session)
    service = OrganizationService(repo)
    
    # Create
    org = await service.register_organization("Cyberdyne Systems", "admin")
    assert org.display_name == "Cyberdyne Systems"
    
    # Retrieve
    retrieved = await repo.get_by_grn(org.grn)
    assert retrieved.display_name == "Cyberdyne Systems"