"""KnowledgeRetriever: vector retrieval, keyword fallback, graceful failure."""
import pytest

from gabriel.gateway.prompt import ContextBlock
from gabriel.knowledge.retrieval import KnowledgeRetriever
from gabriel.knowledge.vector_store import ChunkVectorStore

from .conftest import FakeEmbedder

ORG = "test-org"
DOC = f"grn:{ORG}:document/doc-1:1"
SOURCE = f"grn:{ORG}:knowledge_source/src-1:1"


async def _seed_chunks(session, embedder):
    store = ChunkVectorStore(session)
    texts = [
        "gabriel stores embeddings in pgvector",
        "the cafeteria serves lunch at noon",
    ]
    vectors = await embedder.embed(texts)
    for i, (text, vec) in enumerate(zip(texts, vectors)):
        await store.add_chunk(
            org_id=ORG, document_grn=DOC, knowledge_source_grn=SOURCE,
            chunk_index=i, content=text, token_count=len(text.split()),
            embedding=vec, embedding_model=embedder.model,
            metadata={"filename": "handbook.txt"},
        )
    await session.commit()


@pytest.mark.asyncio
async def test_retrieve_returns_context_blocks(session_factory, fake_embedder):
    async with session_factory() as session:
        await _seed_chunks(session, fake_embedder)

    retriever = KnowledgeRetriever(session_factory, embedder=fake_embedder)
    blocks = await retriever.retrieve(
        org_id=ORG,
        query="pgvector embeddings",
        knowledge_source_grns=[SOURCE],
        limit=1,
    )
    assert len(blocks) == 1
    assert isinstance(blocks[0], ContextBlock)
    assert blocks[0].source.startswith("knowledge:handbook.txt#chunk")
    assert "pgvector" in blocks[0].content


@pytest.mark.asyncio
async def test_retrieve_falls_back_to_keyword_search(session_factory, fake_embedder):
    async with session_factory() as session:
        await _seed_chunks(session, fake_embedder)

    failing = FakeEmbedder(fail=True)
    retriever = KnowledgeRetriever(session_factory, embedder=failing)
    blocks = await retriever.retrieve(org_id=ORG, query="cafeteria")
    assert len(blocks) == 1
    assert "cafeteria" in blocks[0].content


@pytest.mark.asyncio
async def test_retrieve_never_raises(fake_embedder):
    def broken_factory():
        raise RuntimeError("db down")

    retriever = KnowledgeRetriever(broken_factory, embedder=fake_embedder)
    blocks = await retriever.retrieve(org_id=ORG, query="anything")
    assert blocks == []


@pytest.mark.asyncio
async def test_retrieve_respects_max_chars(session_factory, fake_embedder):
    async with session_factory() as session:
        store = ChunkVectorStore(session)
        vec = (await fake_embedder.embed(["long text"]))[0]
        for i in range(3):
            await store.add_chunk(
                org_id=ORG, document_grn=DOC, knowledge_source_grn=None,
                chunk_index=i, content="long text " * 50, token_count=100,
                embedding=vec,
            )
        await session.commit()

    retriever = KnowledgeRetriever(session_factory, embedder=fake_embedder)
    blocks = await retriever.retrieve(
        org_id=ORG, query="long text", limit=3, max_chars=600
    )
    assert sum(len(b.content) for b in blocks) <= 600
    assert len(blocks) >= 1
