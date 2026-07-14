"""TextChunker: deterministic windowed chunking."""
import pytest

from gabriel.knowledge.chunking import TextChunker


def test_empty_text_yields_no_chunks():
    assert TextChunker(chunk_size=8, chunk_overlap=2).split("") == []
    assert TextChunker(chunk_size=8, chunk_overlap=2).split("   \n  ") == []


def test_short_text_single_chunk():
    chunks = TextChunker(chunk_size=100, chunk_overlap=10).split("hello world")
    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].text == "hello world"
    assert chunks[0].token_count == 2


def test_windows_overlap_and_cover_all_tokens():
    words = [f"w{i}" for i in range(25)]
    chunks = TextChunker(chunk_size=10, chunk_overlap=3).split(" ".join(words))
    assert len(chunks) > 1
    assert chunks[0].token_count == 10
    # Overlap: last 3 tokens of chunk N == first 3 tokens of chunk N+1.
    first_tokens = chunks[0].text.split()
    second_tokens = chunks[1].text.split()
    assert first_tokens[-3:] == second_tokens[:3]
    # Every source token appears somewhere.
    seen = set()
    for chunk in chunks:
        seen.update(chunk.text.split())
    assert seen == set(words)
    # Indices are sequential.
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_invalid_configuration_rejected():
    with pytest.raises(ValueError):
        TextChunker(chunk_size=0, chunk_overlap=0)
    with pytest.raises(ValueError):
        TextChunker(chunk_size=10, chunk_overlap=10)
    with pytest.raises(ValueError):
        TextChunker(chunk_size=10, chunk_overlap=-1)
