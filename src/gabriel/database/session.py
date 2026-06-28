from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from gabriel.database.base import Base  # single source of truth for metadata

DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost/gabriel_core"

engine = create_async_engine(DATABASE_URL, echo=True)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session