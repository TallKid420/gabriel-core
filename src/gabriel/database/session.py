from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from gabriel.database.base import Base  # single source of truth for metadata
from gabriel.logging_config import configure_logging

DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost/gabriel_core"

configure_logging()

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session