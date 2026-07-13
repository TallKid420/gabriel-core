"""Refresh tokens: long-lived, revocable session renewal.

Access tokens (JWTs) are short-lived and stateless. Refresh tokens are the
opposite: opaque, long-lived, stored server-side (hashed), single-use, and
rotated on every refresh. This gives sessions the standard OAuth2-style
lifecycle while keeping the access-token hot path stateless:

    login    → access JWT + refresh token
    refresh  → old refresh token revoked, new pair issued (rotation)
    logout   → refresh token revoked

Security properties
-------------------
* Only a SHA-256 hash of the token is persisted — a database leak does not
  leak usable tokens.
* Rotation with reuse detection: presenting an already-rotated token revokes
  the whole chain (a replayed stolen token cannot mint new sessions).
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from gabriel.database.base import Base
from gabriel.identity.exceptions import AuthenticationFailedError

DEFAULT_REFRESH_TTL_SECONDS = 30 * 24 * 3600  # 30 days


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class RefreshTokenORM(Base):
    __tablename__ = "refresh_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    principal_id: Mapped[str] = mapped_column(String(225), index=True, nullable=False)
    org_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    replaced_by_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class RefreshTokenService:
    """Issue, rotate, and revoke refresh tokens against a database session."""

    def __init__(
        self,
        session: AsyncSession,
        ttl_seconds: int = DEFAULT_REFRESH_TTL_SECONDS,
    ) -> None:
        self.session = session
        self.ttl_seconds = ttl_seconds

    async def issue(
        self, principal_id: str, org_id: str, *, commit: bool = True
    ) -> str:
        """Mint and persist a new refresh token; returns the raw token."""
        raw = secrets.token_urlsafe(48)
        now = utcnow()
        self.session.add(
            RefreshTokenORM(
                token_hash=_hash_token(raw),
                principal_id=principal_id,
                org_id=org_id,
                issued_at=now,
                expires_at=now + timedelta(seconds=self.ttl_seconds),
            )
        )
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return raw

    async def rotate(self, raw_token: str) -> tuple[str, str, str]:
        """Validate ``raw_token``, revoke it, and issue a replacement.

        Returns:
            (new_raw_token, principal_id, org_id) — the principal and org
            needed to mint the new access JWT.

        Raises:
            AuthenticationFailedError: If the token is unknown, expired, or
                already used (reuse triggers chain revocation).
        """
        record = await self._get(raw_token)
        if record is None:
            raise AuthenticationFailedError("Unknown refresh token")

        now = utcnow()
        expires_at = record.expires_at
        if expires_at.tzinfo is None:  # SQLite loses tz info
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if record.revoked_at is not None:
            # Reuse of a rotated token — revoke every descendant in the chain.
            await self._revoke_chain(record)
            await self.session.commit()
            raise AuthenticationFailedError(
                "Refresh token was already used; session chain revoked"
            )
        if expires_at <= now:
            raise AuthenticationFailedError("Refresh token has expired")

        new_raw = secrets.token_urlsafe(48)
        principal_id, org_id = record.principal_id, record.org_id
        record.revoked_at = now
        record.replaced_by_hash = _hash_token(new_raw)
        self.session.add(
            RefreshTokenORM(
                token_hash=record.replaced_by_hash,
                principal_id=principal_id,
                org_id=org_id,
                issued_at=now,
                expires_at=now + timedelta(seconds=self.ttl_seconds),
            )
        )
        await self.session.commit()
        return new_raw, principal_id, org_id

    async def revoke(self, raw_token: str) -> bool:
        """Revoke a refresh token (logout). Returns True if one was revoked."""
        record = await self._get(raw_token)
        if record is None or record.revoked_at is not None:
            return False
        record.revoked_at = utcnow()
        await self.session.commit()
        return True

    async def revoke_all_for_principal(self, principal_id: str) -> int:
        """Revoke every active refresh token for a principal."""
        result = await self.session.execute(
            select(RefreshTokenORM).filter_by(principal_id=principal_id, revoked_at=None)
        )
        records = list(result.scalars().all())
        now = utcnow()
        for record in records:
            record.revoked_at = now
        await self.session.commit()
        return len(records)

    # ── internal ────────────────────────────────────────────────────────────

    async def _get(self, raw_token: str) -> RefreshTokenORM | None:
        result = await self.session.execute(
            select(RefreshTokenORM).filter_by(token_hash=_hash_token(raw_token))
        )
        return result.scalar_one_or_none()

    async def _revoke_chain(self, record: RefreshTokenORM) -> None:
        now = utcnow()
        current: RefreshTokenORM | None = record
        seen: set[str] = set()
        while current is not None and current.token_hash not in seen:
            seen.add(current.token_hash)
            if current.revoked_at is None:
                current.revoked_at = now
            if not current.replaced_by_hash:
                break
            result = await self.session.execute(
                select(RefreshTokenORM).filter_by(token_hash=current.replaced_by_hash)
            )
            current = result.scalar_one_or_none()
