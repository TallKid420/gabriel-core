from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from gabriel.organization.orm import OrganizationORM
from gabriel.resource.exceptions import ResourceNotFoundError


class OrganizationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, org_orm: OrganizationORM) -> OrganizationORM:
        self.session.add(org_orm)
        await self.session.commit()
        await self.session.refresh(org_orm)
        return org_orm

    async def get_by_grn(self, grn: str) -> OrganizationORM:
        result = await self.session.execute(select(OrganizationORM).filter_by(grn=grn))
        org = result.scalar_one_or_none()
        if not org:
            raise ResourceNotFoundError(f"Organization {grn} not found")
        return org

    async def get_by_org_id(self, org_id: str) -> OrganizationORM | None:
        """Return the organization whose tenant id is ``org_id``, or None."""
        result = await self.session.execute(
            select(OrganizationORM).filter_by(org_id=org_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[OrganizationORM]:
        result = await self.session.execute(select(OrganizationORM))
        return list(result.scalars().all())