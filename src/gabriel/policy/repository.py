from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gabriel.policy.orm import PolicyORM
from gabriel.resource.exceptions import ResourceNotFoundError


class PolicyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, policy_orm: PolicyORM) -> PolicyORM:
        self.session.add(policy_orm)
        await self.session.commit()
        await self.session.refresh(policy_orm)
        return policy_orm

    async def get_by_grn(self, grn: str) -> PolicyORM:
        result = await self.session.execute(select(PolicyORM).filter_by(grn=grn))
        policy = result.scalar_one_or_none()
        if not policy:
            raise ResourceNotFoundError(f"Policy {grn} not found")
        return policy

    async def list_for_org(self, org_id: str) -> list[PolicyORM]:
        result = await self.session.execute(select(PolicyORM).filter_by(org_id=org_id))
        return list(result.scalars().all())

    async def list_all(self) -> list[PolicyORM]:
        result = await self.session.execute(select(PolicyORM))
        return list(result.scalars().all())

    async def update(self, policy_orm: PolicyORM) -> PolicyORM:
        existing = await self.get_by_grn(policy_orm.grn)
        existing.org_id = policy_orm.org_id
        existing.resource_type = policy_orm.resource_type
        existing.state = policy_orm.state
        existing.version = policy_orm.version
        existing.created_at = policy_orm.created_at
        existing.updated_at = policy_orm.updated_at
        existing.created_by = policy_orm.created_by
        existing.updated_by = policy_orm.updated_by
        existing.resource_metadata = policy_orm.resource_metadata
        existing.labels = policy_orm.labels
        existing.statements = policy_orm.statements

        await self.session.commit()
        await self.session.refresh(existing)
        return existing

    async def delete(self, grn: str) -> None:
        policy = await self.get_by_grn(grn)
        await self.session.delete(policy)
        await self.session.commit()
