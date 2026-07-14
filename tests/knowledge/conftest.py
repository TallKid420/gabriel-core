"""Shared fixtures for knowledge slice tests (in-memory SQLite)."""
import hashlib
import math

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gabriel.database.base import Base

# Import all ORM models to register them with Base.metadata
import gabriel.events.orm  # noqa: F401
import gabriel.document.orm  # noqa: F401
import gabriel.knowledge.chunk_orm  # noqa: F401
import gabriel.knowledge.source_orm  # noqa: F401

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncSession:
    async with session_factory() as session:
        yield session


class FakeEmbedder:
    """Deterministic embedding provider for tests (no network).

    Vectors are derived from character histograms so that identical texts
    embed identically and similar texts land near each other.
    """

    name = "fake"
    model = "fake-embed"

    def __init__(self, dimensions: int = 16, fail: bool = False):
        self.dimensions = dimensions
        self.fail = fail
        self.calls: list[list[str]] = []

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dimensions
        for token in text.lower().split():
            digest = hashlib.md5(token.encode()).digest()
            idx = digest[0] % self.dimensions
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        from gabriel.knowledge.embeddings import EmbeddingConnectionError

        if self.fail:
            raise EmbeddingConnectionError("fake embedder configured to fail")
        self.calls.append(list(texts))
        return [self._vector(text) for text in texts]


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()
