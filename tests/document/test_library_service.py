"""DocumentLibraryService & DocumentProcessingService (Phase 4)."""
from pathlib import Path

import pytest

from gabriel.document.library import (
    DocumentLibraryService,
    UnsupportedDocumentTypeError,
)
from gabriel.document.models import DocumentStatus
from gabriel.document.processing import DocumentProcessingService
from gabriel.knowledge.chunking import TextChunker
from gabriel.knowledge.vector_store import ChunkVectorStore
from gabriel.resource.exceptions import ResourceNotFoundError
from gabriel.resource.models import ResourceState

ORG = "test-org"
USER = "user-1"
TEXT = b"GABRIEL is an agent platform. It stores document chunks in pgvector."


class FakeEmbedder:
    name = "fake"
    model = "fake-embed"

    async def embed(self, texts):
        return [[float(len(t)), 1.0] for t in texts]


class StubNormalizer:
    def normalize(self, path: str) -> str:
        return f"normalized:{Path(path).suffix}"


@pytest.fixture
def library(db_session, content_store) -> DocumentLibraryService:
    return DocumentLibraryService(db_session, content_store=content_store)


@pytest.mark.asyncio
async def test_upload_txt_document(library):
    document = await library.upload_document(
        ORG, filename="notes.txt", content=TEXT, created_by=USER, commit=False
    )
    assert str(document.grn).startswith(f"grn:{ORG}:document/")
    assert document.status == DocumentStatus.UPLOADED
    assert document.filename == "notes.txt"
    assert document.byte_size == len(TEXT)
    assert document.content_hash
    assert document.content_pointer and document.raw_pointer

    text = await library.get_document_text(str(document.grn), org_id=ORG)
    assert "pgvector" in text


@pytest.mark.asyncio
async def test_upload_markdown_document(library):
    document = await library.upload_document(
        ORG, filename="readme.md", content=b"# Title\n\nBody text.",
        created_by=USER, commit=False,
    )
    text = await library.get_document_text(str(document.grn), org_id=ORG)
    assert "Title" in text


@pytest.mark.asyncio
async def test_unsupported_extension_rejected(library):
    with pytest.raises(UnsupportedDocumentTypeError):
        await library.upload_document(
            ORG, filename="binary.exe", content=b"MZ", created_by=USER, commit=False
        )


@pytest.mark.asyncio
async def test_list_and_get_are_org_scoped(library):
    document = await library.upload_document(
        ORG, filename="a.txt", content=TEXT, created_by=USER, commit=False
    )
    items, total = await library.list_documents(ORG)
    assert total == 1 and str(items[0].grn) == str(document.grn)

    items, total = await library.list_documents("other-org")
    assert total == 0
    with pytest.raises(ResourceNotFoundError):
        await library.get_document(str(document.grn), org_id="other-org")


@pytest.mark.asyncio
async def test_processing_creates_embedded_chunks(db_session, library):
    document = await library.upload_document(
        ORG, filename="a.txt", content=TEXT, created_by=USER, commit=False
    )
    processor = DocumentProcessingService(
        db_session,
        library=library,
        chunker=TextChunker(chunk_size=5, chunk_overlap=1),
        embedder=FakeEmbedder(),
    )
    result = await processor.process_document(
        str(document.grn), org_id=ORG, processed_by=USER
    )
    assert result.chunk_count > 1
    assert result.embedded is True
    assert result.embedding_model == "fake-embed"
    assert result.document.status == DocumentStatus.PROCESSED
    assert result.document.chunk_count == result.chunk_count

    chunks, total = await ChunkVectorStore(db_session).list_for_document(
        str(document.grn), ORG
    )
    assert total == result.chunk_count
    assert all(c.embedding is not None for c in chunks)
    assert chunks[0].chunk_metadata["filename"] == "a.txt"


@pytest.mark.asyncio
async def test_processing_degrades_without_embedder(db_session, library):
    document = await library.upload_document(
        ORG, filename="a.txt", content=TEXT, created_by=USER, commit=False
    )
    processor = DocumentProcessingService(db_session, library=library, embedder=None)
    result = await processor.process_document(
        str(document.grn), org_id=ORG, processed_by=USER
    )
    assert result.embedded is False
    assert result.chunk_count >= 1
    chunks, _ = await ChunkVectorStore(db_session).list_for_document(
        str(document.grn), ORG
    )
    assert all(c.embedding is None for c in chunks)


@pytest.mark.asyncio
async def test_reprocessing_replaces_chunks(db_session, library):
    document = await library.upload_document(
        ORG, filename="a.txt", content=TEXT, created_by=USER, commit=False
    )
    processor = DocumentProcessingService(
        db_session, library=library, embedder=FakeEmbedder()
    )
    first = await processor.process_document(
        str(document.grn), org_id=ORG, processed_by=USER, chunk_size=3, chunk_overlap=0
    )
    second = await processor.process_document(
        str(document.grn), org_id=ORG, processed_by=USER, chunk_size=50, chunk_overlap=0
    )
    assert second.chunk_count < first.chunk_count
    _, total = await ChunkVectorStore(db_session).list_for_document(
        str(document.grn), ORG
    )
    assert total == second.chunk_count


@pytest.mark.asyncio
async def test_soft_delete_purges_chunks(db_session, library):
    document = await library.upload_document(
        ORG, filename="a.txt", content=TEXT, created_by=USER, commit=False
    )
    processor = DocumentProcessingService(
        db_session, library=library, embedder=FakeEmbedder()
    )
    await processor.process_document(str(document.grn), org_id=ORG, processed_by=USER)

    deleted = await library.delete_document(
        str(document.grn), deleted_by=USER, org_id=ORG
    )
    assert deleted.state == ResourceState.DELETED
    with pytest.raises(ResourceNotFoundError):
        await library.get_document(str(document.grn), org_id=ORG)
    _, total = await ChunkVectorStore(db_session).list_for_document(
        str(document.grn), ORG
    )
    assert total == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("sample.pdf", b"%PDF-1.4\n%stub"),
        ("sample.docx", b"PK\x03\x04\x14\x00\x06\x00"),
    ],
)
async def test_upload_parser_formats_retries_tempfile_cleanup(
    db_session, content_store, monkeypatch, filename, content
):
    library = DocumentLibraryService(
        db_session,
        content_store=content_store,
        normalizer=StubNormalizer(),
    )

    original_unlink = Path.unlink
    calls = {"count": 0}

    def flaky_unlink(self: Path, *, missing_ok: bool = False):
        calls["count"] += 1
        if calls["count"] <= 2:
            raise PermissionError("WinError 32 simulated lock")
        return original_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", flaky_unlink)

    first = await library.upload_document(
        ORG,
        filename=filename,
        content=content,
        created_by=USER,
        commit=False,
    )
    second = await library.upload_document(
        ORG,
        filename=f"again-{filename}",
        content=content,
        created_by=USER,
        commit=False,
    )

    assert first.status == DocumentStatus.UPLOADED
    assert second.status == DocumentStatus.UPLOADED
    assert calls["count"] >= 4


@pytest.mark.asyncio
async def test_upload_parser_formats_does_not_fail_when_cleanup_exhausts_retries(
    db_session, content_store, monkeypatch, caplog
):
    library = DocumentLibraryService(
        db_session,
        content_store=content_store,
        normalizer=StubNormalizer(),
    )

    def always_locked_unlink(self: Path, *, missing_ok: bool = False):
        raise PermissionError("WinError 32 simulated persistent lock")

    monkeypatch.setattr(Path, "unlink", always_locked_unlink)

    with caplog.at_level("WARNING"):
        document = await library.upload_document(
            ORG,
            filename="locked.pdf",
            content=b"%PDF-1.4\n%stub",
            created_by=USER,
            commit=False,
        )

    assert document.status == DocumentStatus.UPLOADED
    assert "Failed to delete temp file" in caplog.text
