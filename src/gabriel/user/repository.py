"""User repository — persistence access for the User resource.

NOTE: All queries are org-scoped where an ``org_id`` is available; tenant
isolation is enforced at the query layer (P-2: isolation by default).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gabriel.resource.exceptions import ResourceNotFoundError
from gabriel.user.orm import UserORM


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_orm: UserORM) -> UserORM:
        """Persist a new user row (caller controls the transaction)."""
        self.session.add(user_orm)
        await self.session.flush()
        return user_orm

    async def get_by_grn(self, grn: str) -> UserORM:
        result = await self.session.execute(select(UserORM).filter_by(grn=grn))
        user = result.scalar_one_or_none()
        if not user:
            raise ResourceNotFoundError(f"User {grn} not found")
        return user

    async def get_by_email(self, email: str, org_id: str | None = None) -> UserORM | None:
        """Look up a user by email, optionally scoped to an organization.

        Without ``org_id`` (login before the tenant is known) the lookup is
        global; if the email exists in multiple orgs the caller must supply
        ``org_id`` to disambiguate.
        """
        stmt = select(UserORM).filter_by(email=email.strip().lower())
        if org_id is not None:
            stmt = stmt.filter_by(org_id=org_id)
        result = await self.session.execute(stmt)
        users = list(result.scalars().all())
        if not users:
            return None
        if len(users) > 1:
            raise ValueError(
                f"Email '{email}' exists in multiple organizations; org_id required"
            )
        return users[0]

    async def get_by_principal_id(self, principal_id: str) -> UserORM | None:
        result = await self.session.execute(
            select(UserORM).filter_by(principal_id=principal_id)
        )
        return result.scalar_one_or_none()

    async def list_for_org(self, org_id: str) -> list[UserORM]:
        result = await self.session.execute(
            select(UserORM).filter_by(org_id=org_id).order_by(UserORM.created_at)
        )
        return list(result.scalars().all())

    async def update(self, user_orm: UserORM) -> UserORM:
        """Flush pending changes on a managed ORM instance."""
        await self.session.flush()
        return user_orm
