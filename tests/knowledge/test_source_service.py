"""KnowledgeSourceService: CRUD, attach/detach, chunk relabelling."""
import pytest

from gabriel.document.library import DocumentLibraryService
from gabriel.knowledge.source_models import KnowledgeSourceStatus
from gabriel.knowledge.source_service import KnowledgeSourceService
from gabriel.knowledge.vector_store import ChunkVectorStore
from gabriel.resource.exceptions import ResourceNotFoundError
from gabriel.resource.models import ResourceState

ORG = "test-org"
USER = "user-1"


async def _upload_doc(session, tmp_path, name="doc.txt", text=b"hello knowledge world"):
    from gabriel.document.content_store import DiskContentStore

    library = DocumentLibraryService(
        session, content_store=DiskContentStore(tmp_path / "content")
    )
    return await library.upload_document(
        ORG, filename=name, content=text, created_by=USER, commit=False
    )


@pytest.mark.asyncio
async def test_create_get_list_source(db_session):
    service = KnowledgeSourceService(db_session)
    source = await service.create_source(
        ORG, "Handbook", created_by=USER, description="Company handbook"
    )
    assert str(source.grn).startswith(f"grn:{ORG}:knowledge_source/")
    assert source.status == KnowledgeSourceStatus.ACTIVE
    assert source.document_count == 0

    fetched = await service.get_source(str(source.grn), org_id=ORG)
    assert fetched.name == "Handbook"

    items, total = await service.list_sources(ORG)
    assert total == 1 and items[0].name == "Handbook"

    # Org isolation
    with pytest.raises(ResourceNotFoundError):
        await service.get_source(str(source.grn), org_id="other-org")


@pytest.mark.asyncio
async def test_update_and_soft_delete_source(db_session):
    service = KnowledgeSourceService(db_session)
    source = await service.create_source(ORG, "Old", created_by=USER)
    updated = await service.update_source(
        str(source.grn), updated_by=USER, org_id=ORG,
        name="New", status="archived", metadata={"k": "v"},
    )
    assert updated.name == "New"
    assert updated.status == KnowledgeSourceStatus.ARCHIVED
    assert updated.version == source.version + 1
    assert updated.metadata["k"] == "v"

    deleted = await service.delete_source(str(source.grn), deleted_by=USER, org_id=ORG)
    assert deleted.state == ResourceState.DELETED
    with pytest.raises(ResourceNotFoundError):
        await service.get_source(str(source.grn), org_id=ORG)


@pytest.mark.asyncio
async def test_attach_and_detach_document(db_session, tmp_path):
    document = await _upload_doc(db_session, tmp_path)
    service = KnowledgeSourceService(db_session)
    source = await service.create_source(ORG, "Docs", created_by=USER, commit=False)

    # Give the document some chunks to relabel.
    store = ChunkVectorStore(db_session)
    await store.add_chunk(
        org_id=ORG, document_grn=str(document.grn), knowledge_source_grn=None,
        chunk_index=0, content="hello", token_count=1, embedding=None,
    )

    attached = await service.attach_document(
        str(source.grn), str(document.grn), org_id=ORG, updated_by=USER, commit=False
    )
    assert attached.knowledge_source_grn == str(source.grn)
    page, _ = await store.list_for_document(str(document.grn), ORG)
    assert page[0].knowledge_source_grn == str(source.grn)

    refreshed = await service.get_source(str(source.grn), org_id=ORG)
    assert refreshed.document_count == 1

    docs, total = await service.list_documents(str(source.grn), org_id=ORG)
    assert total == 1 and str(docs[0].grn) == str(document.grn)

    detached = await service.detach_document(
        str(source.grn), str(document.grn), org_id=ORG, updated_by=USER, commit=False
    )
    assert detached.knowledge_source_grn is None
    page, _ = await store.list_for_document(str(document.grn), ORG)
    assert page[0].knowledge_source_grn is None
    refreshed = await service.get_source(str(source.grn), org_id=ORG)
    assert refreshed.document_count == 0


@pytest.mark.asyncio
async def test_delete_source_detaches_documents(db_session, tmp_path):
    document = await _upload_doc(db_session, tmp_path)
    service = KnowledgeSourceService(db_session)
    source = await service.create_source(ORG, "Docs", created_by=USER, commit=False)
    await service.attach_document(
        str(source.grn), str(document.grn), org_id=ORG, updated_by=USER, commit=False
    )

    await service.delete_source(
        str(source.grn), deleted_by=USER, org_id=ORG, commit=False
    )
    refreshed_doc = await service.documents.get_document(
        str(document.grn), org_id=ORG
    )
    assert refreshed_doc.knowledge_source_grn is None
