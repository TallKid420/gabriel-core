"""Shared fixtures for document slice tests (in-memory SQLite + tmp store)."""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gabriel.database.base import Base
from gabriel.document.content_store import DiskContentStore

# Import all ORM models to register them with Base.metadata
import gabriel.events.orm  # noqa: F401
import gabriel.document.orm  # noqa: F401
import gabriel.knowledge.chunk_orm  # noqa: F401
import gabriel.knowledge.source_orm  # noqa: F401

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def content_store(tmp_path) -> DiskContentStore:
    return DiskContentStore(tmp_path / "content")
