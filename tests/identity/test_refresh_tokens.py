"""Refresh token lifecycle: issue → rotate → reuse detection → revoke."""
from __future__ import annotations

import pytest

from gabriel.identity.exceptions import AuthenticationFailedError
from gabriel.identity.refresh import RefreshTokenService

PRINCIPAL = "principal://acme/user/alice"
ORG = "acme"


@pytest.mark.asyncio
async def test_issue_and_rotate(db_session):
    service = RefreshTokenService(db_session)
    raw = await service.issue(PRINCIPAL, ORG)
    assert isinstance(raw, str) and len(raw) > 30

    new_raw, principal_id, org_id = await service.rotate(raw)
    assert new_raw != raw
    assert principal_id == PRINCIPAL
    assert org_id == ORG


@pytest.mark.asyncio
async def test_reuse_of_rotated_token_revokes_chain(db_session):
    service = RefreshTokenService(db_session)
    raw = await service.issue(PRINCIPAL, ORG)
    new_raw, _, _ = await service.rotate(raw)

    # Replaying the old token must fail AND revoke the descendant.
    with pytest.raises(AuthenticationFailedError):
        await service.rotate(raw)
    with pytest.raises(AuthenticationFailedError):
        await service.rotate(new_raw)


@pytest.mark.asyncio
async def test_unknown_token_rejected(db_session):
    service = RefreshTokenService(db_session)
    with pytest.raises(AuthenticationFailedError):
        await service.rotate("definitely-not-a-token")


@pytest.mark.asyncio
async def test_expired_token_rejected(db_session):
    service = RefreshTokenService(db_session, ttl_seconds=-1)
    raw = await service.issue(PRINCIPAL, ORG)
    with pytest.raises(AuthenticationFailedError, match="expired"):
        await service.rotate(raw)


@pytest.mark.asyncio
async def test_revoke_blocks_rotation(db_session):
    service = RefreshTokenService(db_session)
    raw = await service.issue(PRINCIPAL, ORG)
    assert await service.revoke(raw) is True
    assert await service.revoke(raw) is False  # already revoked
    with pytest.raises(AuthenticationFailedError):
        await service.rotate(raw)


@pytest.mark.asyncio
async def test_revoke_all_for_principal(db_session):
    service = RefreshTokenService(db_session)
    await service.issue(PRINCIPAL, ORG)
    await service.issue(PRINCIPAL, ORG)
    await service.issue("principal://acme/user/bob", ORG)

    revoked = await service.revoke_all_for_principal(PRINCIPAL)
    assert revoked == 2
