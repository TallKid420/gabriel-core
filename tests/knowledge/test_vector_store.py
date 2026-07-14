"""ChunkVectorStore: similarity search (SQLite fallback path) & chunk CRUD."""
import pytest

from gabriel.knowledge.vector_store import ChunkVectorStore, cosine_similarity

ORG = "test-org"
DOC = f"grn:{ORG}:document/doc-1:1"
OTHER_DOC = f"grn:{ORG}:document/doc-2:1"
SOURCE = f"grn:{ORG}:knowledge_source/src-1:1"


def test_cosine_similarity_basics():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([], [1.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


@pytest.mark.asyncio
async def test_add_list_count_and_delete(db_session):
    store = ChunkVectorStore(db_session)
    for i in range(3):
        await store.add_chunk(
            org_id=ORG,
            document_grn=DOC,
            knowledge_source_grn=None,
            chunk_index=i,
            content=f"chunk {i}",
            token_count=2,
            embedding=[float(i), 1.0],
            embedding_model="fake",
        )
    assert await store.count_for_document(DOC, ORG) == 3
    page, total = await store.list_for_document(DOC, ORG, limit=2, offset=1)
    assert total == 3
    assert [c.chunk_index for c in page] == [1, 2]

    deleted = await store.delete_for_document(DOC, ORG)
    assert deleted == 3
    assert await store.count_for_document(DOC, ORG) == 0


@pytest.mark.asyncio
async def test_search_ranks_by_cosine_similarity(db_session, fake_embedder):
    store = ChunkVectorStore(db_session)
    texts = [
        "the quick brown fox jumps",
        "postgres vector database indexing",
        "cooking pasta with tomato sauce",
    ]
    vectors = await fake_embedder.embed(texts)
    for i, (text, vec) in enumerate(zip(texts, vectors)):
        await store.add_chunk(
            org_id=ORG,
            document_grn=DOC,
            knowledge_source_grn=SOURCE,
            chunk_index=i,
            content=text,
            token_count=len(text.split()),
            embedding=vec,
            embedding_model=fake_embedder.model,
        )

    query_vec = (await fake_embedder.embed(["vector database postgres"]))[0]
    results = await store.search(org_id=ORG, query_embedding=query_vec, limit=2)
    assert len(results) == 2
    assert results[0].content == "postgres vector database indexing"
    assert results[0].score >= results[1].score


@pytest.mark.asyncio
async def test_search_filters_by_source_document_and_org(db_session, fake_embedder):
    store = ChunkVectorStore(db_session)
    vec = (await fake_embedder.embed(["shared text"]))[0]
    await store.add_chunk(
        org_id=ORG, document_grn=DOC, knowledge_source_grn=SOURCE,
        chunk_index=0, content="in source", token_count=2, embedding=vec,
    )
    await store.add_chunk(
        org_id=ORG, document_grn=OTHER_DOC, knowledge_source_grn=None,
        chunk_index=0, content="no source", token_count=2, embedding=vec,
    )
    await store.add_chunk(
        org_id="other-org", document_grn="grn:other-org:document/x:1",
        knowledge_source_grn=None, chunk_index=0, content="other org",
        token_count=2, embedding=vec,
    )

    by_source = await store.search(
        org_id=ORG, query_embedding=vec, knowledge_source_grns=[SOURCE]
    )
    assert [r.content for r in by_source] == ["in source"]

    by_doc = await store.search(
        org_id=ORG, query_embedding=vec, document_grns=[OTHER_DOC]
    )
    assert [r.content for r in by_doc] == ["no source"]

    all_org = await store.search(org_id=ORG, query_embedding=vec)
    assert len(all_org) == 2  # other-org chunk never leaks


@pytest.mark.asyncio
async def test_keyword_search_fallback(db_session):
    store = ChunkVectorStore(db_session)
    await store.add_chunk(
        org_id=ORG, document_grn=DOC, knowledge_source_grn=None,
        chunk_index=0, content="GABRIEL uses pgvector for retrieval",
        token_count=5, embedding=None,
    )
    await store.add_chunk(
        org_id=ORG, document_grn=DOC, knowledge_source_grn=None,
        chunk_index=1, content="unrelated content", token_count=2, embedding=None,
    )
    results = await store.keyword_search(org_id=ORG, query="pgvector")
    assert len(results) == 1
    assert "pgvector" in results[0].content


@pytest.mark.asyncio
async def test_assign_knowledge_source_relabels_chunks(db_session):
    store = ChunkVectorStore(db_session)
    for i in range(2):
        await store.add_chunk(
            org_id=ORG, document_grn=DOC, knowledge_source_grn=None,
            chunk_index=i, content=f"c{i}", token_count=1, embedding=None,
        )
    updated = await store.assign_knowledge_source(DOC, ORG, SOURCE)
    assert updated == 2
    page, _ = await store.list_for_document(DOC, ORG)
    assert all(c.knowledge_source_grn == SOURCE for c in page)
