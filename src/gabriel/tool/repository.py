from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from gabriel.tool.orm import ToolORM
from gabriel.resource.exceptions import ResourceNotFoundError

class ToolRepository:
    ...