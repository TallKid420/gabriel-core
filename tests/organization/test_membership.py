"""Org membership: add, change role, remove, last-owner guard."""
from __future__ import annotations

import pytest

from gabriel.identity.roles import OrgRole
from gabriel.organization.membership_service import MembershipService
from gabriel.resource.exceptions import DuplicateResourceError, ResourceNotFoundError

ORG = "acme"
ALICE = "principal://acme/user/alice"
BOB = "principal://acme/user/bob"


@pytest.mark.asyncio
async def test_add_and_list_members(db_session):
    service = MembershipService(db_session)
    await service.add_member(ORG, ALICE, OrgRole.OWNER, added_by="system")
    await service.add_member(ORG, BOB, OrgRole.MEMBER, added_by=ALICE)

    members = await service.list_members(ORG)
    assert {m.principal_id for m in members} == {ALICE, BOB}
    assert {m.role for m in members} == {"owner", "member"}


@pytest.mark.asyncio
async def test_duplicate_membership_rejected(db_session):
    service = MembershipService(db_session)
    await service.add_member(ORG, ALICE, OrgRole.MEMBER, added_by="system")
    with pytest.raises(DuplicateResourceError):
        await service.add_member(ORG, ALICE, OrgRole.ADMIN, added_by="system")


@pytest.mark.asyncio
async def test_change_role(db_session):
    service = MembershipService(db_session)
    await service.add_member(ORG, ALICE, OrgRole.MEMBER, added_by="system")
    membership = await service.change_role(ORG, ALICE, OrgRole.ADMIN, changed_by="system")
    assert membership.role == OrgRole.ADMIN.value


@pytest.mark.asyncio
async def test_remove_member(db_session):
    service = MembershipService(db_session)
    await service.add_member(ORG, ALICE, OrgRole.OWNER, added_by="system")
    await service.add_member(ORG, BOB, OrgRole.MEMBER, added_by=ALICE)
    await service.remove_member(ORG, BOB, removed_by=ALICE)
    members = await service.list_members(ORG)
    assert {m.principal_id for m in members} == {ALICE}


@pytest.mark.asyncio
async def test_cannot_remove_last_owner(db_session):
    service = MembershipService(db_session)
    await service.add_member(ORG, ALICE, OrgRole.OWNER, added_by="system")
    with pytest.raises(ValueError, match="last owner"):
        await service.remove_member(ORG, ALICE, removed_by=ALICE)


@pytest.mark.asyncio
async def test_unknown_membership_raises(db_session):
    service = MembershipService(db_session)
    with pytest.raises(ResourceNotFoundError):
        await service.change_role(ORG, "principal://acme/user/ghost", OrgRole.ADMIN, changed_by="x")


@pytest.mark.asyncio
async def test_memberships_for_principal_spans_orgs(db_session):
    service = MembershipService(db_session)
    await service.add_member("acme", ALICE, OrgRole.OWNER, added_by="system")
    await service.add_member("globex", ALICE, OrgRole.MEMBER, added_by="system")
    memberships = await service.memberships_for_principal(ALICE)
    assert {m.org_id for m in memberships} == {"acme", "globex"}
