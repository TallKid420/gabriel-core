from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from gabriel.identity.principal import Principal
from gabriel.identity.orm import PrincipalORM
from gabriel.identity.mappers import orm_to_domain, domain_to_orm


# NOTE: Must always be org-scoped and enforce isolation at the query layer
class PrincipalRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, principal: Principal) -> Principal:
        """Create a new principal in the database."""
        orm = domain_to_orm(principal)
        self.session.add(orm)
        await self.session.commit()
        await self.session.refresh(orm)
        return orm_to_domain(orm)

    async def get_by_id(self, principal_id: str) -> Principal | None:
        """Retrieve a principal by ID from the database."""
        result = await self.session.execute(
            select(PrincipalORM).filter_by(principal_id=principal_id)
        )
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        return orm_to_domain(orm)

    async def list_for_org(self, org_id: str) -> list[Principal]:
        """List all principals for a given organization."""
        result = await self.session.execute(
            select(PrincipalORM).filter_by(org_id=org_id)
        )
        orms = result.scalars().all()
        return [orm_to_domain(orm) for orm in orms]