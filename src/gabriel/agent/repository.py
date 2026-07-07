from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gabriel.agent.orm import AgentORM
from gabriel.resource.exceptions import ResourceNotFoundError


class AgentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, agent_orm: AgentORM) -> AgentORM:
        self.session.add(agent_orm)
        await self.session.commit()
        await self.session.refresh(agent_orm)
        return agent_orm

    async def get_by_grn(self, grn: str) -> AgentORM:
        result = await self.session.execute(select(AgentORM).filter_by(grn=grn))
        agent = result.scalar_one_or_none()
        if not agent:
            raise ResourceNotFoundError(f"Agent {grn} not found")
        return agent

    async def list_for_org(self, org_id: str) -> list[AgentORM]:
        result = await self.session.execute(select(AgentORM).filter_by(org_id=org_id))
        return list(result.scalars().all())

    async def list_all(self) -> list[AgentORM]:
        result = await self.session.execute(select(AgentORM))
        return list(result.scalars().all())

    async def update(self, agent_orm: AgentORM) -> AgentORM:
        existing = await self.get_by_grn(agent_orm.grn)
        existing.org_id = agent_orm.org_id
        existing.resource_type = agent_orm.resource_type
        existing.state = agent_orm.state
        existing.version = agent_orm.version
        existing.created_at = agent_orm.created_at
        existing.updated_at = agent_orm.updated_at
        existing.created_by = agent_orm.created_by
        existing.updated_by = agent_orm.updated_by
        existing.resource_metadata = agent_orm.resource_metadata
        existing.labels = agent_orm.labels
        existing.specification = agent_orm.specification
        existing.enabled = agent_orm.enabled

        await self.session.commit()
        await self.session.refresh(existing)
        return existing

    async def delete(self, grn: str) -> None:
        agent = await self.get_by_grn(grn)
        await self.session.delete(agent)
        await self.session.commit()
