from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from gabriel.tool.orm import ToolORM
from gabriel.resource.exceptions import ResourceNotFoundError


class ToolRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, tool_orm: ToolORM) -> ToolORM:
        self.session.add(tool_orm)
        await self.session.commit()
        await self.session.refresh(tool_orm)
        return tool_orm

    async def get_by_grn(self, grn: str) -> ToolORM:
        result = await self.session.execute(select(ToolORM).filter_by(grn=grn))
        tool = result.scalar_one_or_none()
        if not tool:
            raise ResourceNotFoundError(f"Tool {grn} not found")
        return tool

    async def list_for_org(self, org_id: str) -> list[ToolORM]:
        result = await self.session.execute(select(ToolORM).filter_by(org_id=org_id))
        return list(result.scalars().all())

    async def list_all(self) -> list[ToolORM]:
        result = await self.session.execute(select(ToolORM))
        return list(result.scalars().all())

    async def update(self, tool_orm: ToolORM) -> ToolORM:
        existing = await self.get_by_grn(tool_orm.grn)
        existing.org_id = tool_orm.org_id
        existing.resource_type = tool_orm.resource_type
        existing.state = tool_orm.state
        existing.version = tool_orm.version
        existing.created_at = tool_orm.created_at
        existing.updated_at = tool_orm.updated_at
        existing.created_by = tool_orm.created_by
        existing.updated_by = tool_orm.updated_by
        existing.resource_metadata = tool_orm.resource_metadata
        existing.labels = tool_orm.labels
        existing.name = tool_orm.name
        existing.description = tool_orm.description
        existing.category = tool_orm.category
        existing.input_schema = tool_orm.input_schema
        existing.output_schema = tool_orm.output_schema
        existing.safety_level = tool_orm.safety_level
        existing.required_capabilities = tool_orm.required_capabilities

        await self.session.commit()
        await self.session.refresh(existing)
        return existing

    async def delete(self, grn: str) -> None:
        tool = await self.get_by_grn(grn)
        await self.session.delete(tool)
        await self.session.commit()