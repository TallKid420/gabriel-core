"""Repository for ExternalIntegration persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gabriel.integration.models import IntegrationType
from gabriel.integration.orm import ExternalIntegrationORM
from gabriel.resource.exceptions import ResourceNotFoundError


class ExternalIntegrationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, orm: ExternalIntegrationORM) -> ExternalIntegrationORM:
        self.session.add(orm)
        await self.session.commit()
        await self.session.refresh(orm)
        return orm

    async def get_by_grn(self, grn: str) -> ExternalIntegrationORM:
        result = await self.session.execute(
            select(ExternalIntegrationORM).filter_by(grn=grn)
        )
        obj = result.scalar_one_or_none()
        if obj is None:
            raise ResourceNotFoundError(f"ExternalIntegration '{grn}' not found")
        return obj

    async def get_for_org_and_type(
        self,
        org_id: str,
        integration_type: IntegrationType,
    ) -> ExternalIntegrationORM | None:
        """Return the active integration record for an org + type, or None."""
        result = await self.session.execute(
            select(ExternalIntegrationORM).filter_by(
                org_id=org_id,
                integration_type=integration_type.value,
                is_active=True,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_org(self, org_id: str) -> list[ExternalIntegrationORM]:
        result = await self.session.execute(
            select(ExternalIntegrationORM).filter_by(org_id=org_id)
        )
        return list(result.scalars().all())

    async def update(
        self, orm: ExternalIntegrationORM
    ) -> ExternalIntegrationORM:
        existing = await self.get_by_grn(orm.grn)
        existing.state = orm.state
        existing.version = orm.version
        existing.updated_at = orm.updated_at
        existing.updated_by = orm.updated_by
        existing.resource_metadata = orm.resource_metadata
        existing.labels = orm.labels
        existing.display_name = orm.display_name
        existing.credentials = orm.credentials
        existing.scopes = orm.scopes
        existing.is_active = orm.is_active
        await self.session.commit()
        await self.session.refresh(existing)
        return existing

    async def delete(self, grn: str) -> None:
        obj = await self.get_by_grn(grn)
        await self.session.delete(obj)
        await self.session.commit()
