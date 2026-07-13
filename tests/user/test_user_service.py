"""UserService: registration, authentication, lifecycle (single-transaction outbox)."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from gabriel.events.orm import EventORM
from gabriel.identity.exceptions import AuthenticationFailedError
from gabriel.identity.models import Capability
from gabriel.identity.repository import PrincipalRepository
from gabriel.identity.roles import OrgRole
from gabriel.organization.membership_service import MembershipService
from gabriel.resource.exceptions import DuplicateResourceError
from gabriel.resource.models import ResourceState
from gabriel.user.service import UserService

ORG = "acme"


async def _register(db_session, email="alice@acme.io", role=OrgRole.MEMBER, org=ORG):
    return await UserService(db_session).register_user(
        org_id=org,
        email=email,
        password="hunter2hunter2",
        display_name="Alice Doe",
        role=role,
        created_by="system",
    )


@pytest.mark.asyncio
async def test_register_creates_user_principal_membership_and_event(db_session):
    user = await _register(db_session, role=OrgRole.OWNER)

    # User resource
    assert user.org_id == ORG
    assert user.email == "alice@acme.io"
    assert str(user.grn).startswith(f"grn:{ORG}:user/")
    assert user.state == ResourceState.ACTIVE

    # Mirrored principal with role-derived capabilities
    principal = await PrincipalRepository(db_session).get_by_id(user.principal_id)
    assert principal is not None
    assert principal.organization_id == ORG
    assert Capability.MANAGE_PRINCIPALS in principal.capabilities

    # Membership carries the owner role
    membership = await MembershipService(db_session).get_membership(
        ORG, user.principal_id
    )
    assert membership.role == OrgRole.OWNER.value

    # Outbox event persisted in the same transaction
    result = await db_session.execute(
        select(EventORM).filter_by(resource_grn=str(user.grn))
    )
    events = list(result.scalars().all())
    assert any(e.type == "resource_created" for e in events)


@pytest.mark.asyncio
async def test_password_hash_never_in_public_view(db_session):
    user = await _register(db_session)
    view = user.public_view()
    assert "password_hash" not in view
    assert "password" not in str(view)
    # And excluded from model dumps too
    assert "password_hash" not in user.model_dump()


@pytest.mark.asyncio
async def test_duplicate_email_in_same_org_rejected(db_session):
    await _register(db_session)
    with pytest.raises(DuplicateResourceError):
        await _register(db_session)


@pytest.mark.asyncio
async def test_same_email_allowed_in_different_orgs(db_session):
    await _register(db_session, org="acme")
    other = await _register(db_session, org="globex")
    assert other.org_id == "globex"


@pytest.mark.asyncio
async def test_authenticate_success_and_failure(db_session):
    await _register(db_session)
    service = UserService(db_session)

    user = await service.authenticate("alice@acme.io", "hunter2hunter2")
    assert user.email == "alice@acme.io"

    with pytest.raises(AuthenticationFailedError, match="Invalid email or password"):
        await service.authenticate("alice@acme.io", "wrong-password")
    with pytest.raises(AuthenticationFailedError, match="Invalid email or password"):
        await service.authenticate("ghost@acme.io", "hunter2hunter2")


@pytest.mark.asyncio
async def test_deactivated_user_cannot_authenticate(db_session):
    user = await _register(db_session)
    service = UserService(db_session)
    await service.deactivate_user(str(user.grn), deactivated_by="system")

    with pytest.raises(AuthenticationFailedError):
        await service.authenticate("alice@acme.io", "hunter2hunter2")


@pytest.mark.asyncio
async def test_change_password(db_session):
    user = await _register(db_session)
    service = UserService(db_session)

    await service.change_password(
        str(user.grn), "hunter2hunter2", "new-password-123", changed_by="system"
    )
    assert await service.authenticate("alice@acme.io", "new-password-123")

    with pytest.raises(AuthenticationFailedError):
        await service.change_password(
            str(user.grn), "wrong-current", "whatever-else", changed_by="system"
        )


@pytest.mark.asyncio
async def test_update_user_bumps_version(db_session):
    user = await _register(db_session)
    service = UserService(db_session)
    updated = await service.update_user(
        str(user.grn), updated_by="system", display_name="Alice Updated"
    )
    assert updated.display_name == "Alice Updated"
    assert updated.version == user.version + 1
