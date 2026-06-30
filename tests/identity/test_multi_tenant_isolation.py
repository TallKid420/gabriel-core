"""Tests for multi-tenant isolation (Phase-0 Readiness Review gate)."""
import pytest
from gabriel.identity.models import PrincipalType, Capability
from gabriel.identity.service import PrincipalService
from gabriel.identity.repository import PrincipalRepository
from gabriel.resource.bootstrap import register_core_resource_types
from gabriel.resource.registry import ResourceRegistry


@pytest.mark.asyncio
async def test_list_for_org_returns_only_org_principals(db_session):
    """
    Readiness Review Exit Gate:
    Create principals in org A and org B.
    list_for_org("A") returns only A's rows.
    Cross-org query returns 0 rows.
    """
    register_core_resource_types()
    
    
    repo = PrincipalRepository(db_session)
    service = PrincipalService(repo)
    
    # Create principals in org A
    org_a_principal1 = await service.register_principal(
        org_id="org-a",
        principal_type=PrincipalType.USER,
        principal_identifier="alice",
        display_name="Alice A",
        capabilities=[Capability.READ_RESOURCE],
    )
    
    org_a_principal2 = await service.register_principal(
        org_id="org-a",
        principal_type=PrincipalType.AGENT,
        principal_identifier="bot-a",
        display_name="Bot A",
        capabilities=[],
    )
    
    # Create principals in org B
    org_b_principal1 = await service.register_principal(
        org_id="org-b",
        principal_type=PrincipalType.USER,
        principal_identifier="bob",
        display_name="Bob B",
        capabilities=[Capability.WRITE_RESOURCE],
    )
    
    org_b_principal2 = await service.register_principal(
        org_id="org-b",
        principal_type=PrincipalType.AGENT,
        principal_identifier="bot-b",
        display_name="Bot B",
        capabilities=[],
    )
    
    # Query org A: should return only A's principals
    org_a_list = await service.list_principals_for_org("org-a")
    assert len(org_a_list) == 2
    assert {p.display_name for p in org_a_list} == {"Alice A", "Bot A"}
    assert all(p.organization_id == "org-a" for p in org_a_list)
    
    # Query org B: should return only B's principals
    org_b_list = await service.list_principals_for_org("org-b")
    assert len(org_b_list) == 2
    assert {p.display_name for p in org_b_list} == {"Bob B", "Bot B"}
    assert all(p.organization_id == "org-b" for p in org_b_list)
    
    # Cross-org query: should return 0 rows
    cross_org = await service.list_principals_for_org("non-existent-org")
    assert len(cross_org) == 0


@pytest.mark.asyncio
async def test_cross_org_isolation_no_leakage(db_session):
    """
    Ensure that querying one org never returns another org's data.
    Create many principals across multiple orgs and verify perfect isolation.
    """
    register_core_resource_types()
    
    
    repo = PrincipalRepository(db_session)
    service = PrincipalService(repo)
    
    orgs = ["tenant-1", "tenant-2", "tenant-3"]
    principals_per_org = 3
    
    # Create principals for each org
    created = {}
    for org_id in orgs:
        created[org_id] = []
        for i in range(principals_per_org):
            principal = await service.register_principal(
                org_id=org_id,
                principal_type=PrincipalType.USER,
                principal_identifier=f"user-{i}",
                display_name=f"User {i} ({org_id})",
                capabilities=[],
            )
            created[org_id].append(principal)
    
    # Verify each org query returns exactly its principals
    for org_id in orgs:
        org_list = await service.list_principals_for_org(org_id)
        assert len(org_list) == principals_per_org
        
        org_names = {p.display_name for p in org_list}
        expected_names = {f"User {i} ({org_id})" for i in range(principals_per_org)}
        assert org_names == expected_names
        
        # Verify no principal from other orgs is included
        for p in org_list:
            assert p.organization_id == org_id
            for other_org in orgs:
                if other_org != org_id:
                    assert other_org not in p.display_name


@pytest.mark.asyncio
async def test_empty_org_returns_zero(db_session):
    """Test that querying an org with no principals returns empty list."""
    register_core_resource_types()
    
    
    repo = PrincipalRepository(db_session)
    service = PrincipalService(repo)
    
    # Query non-existent org
    result = await service.list_principals_for_org("empty-org")
    assert result == []
    assert len(result) == 0
