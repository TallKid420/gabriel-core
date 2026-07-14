"""Deterministic text chunking for the knowledge pipeline.

Extracted from ``DocumentIngestionService._chunk_tokens`` (Task 3.4) so both
the legacy RAG-into-memory path and the Phase-4 document-chunk pipeline share
one implementation. A "token" is a whitespace-delimited word — cheap, stable,
and good enough for windowing; embedding models do their own tokenisation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_CHUNK_SIZE = int(os.environ.get("GABRIEL_CHUNK_SIZE", "512"))
DEFAULT_CHUNK_OVERLAP = int(os.environ.get("GABRIEL_CHUNK_OVERLAP", "64"))


@dataclass(frozen=True)
class Chunk:
    """One contiguous window of a document's normalized text."""

    index: int
    """Zero-based position of this chunk within the source document."""

    text: str
    """The chunk content."""

    token_count: int
    """Number of whitespace tokens in :attr:`text`."""


@dataclass(frozen=True)
class TextChunker:
    """Splits text into overlapping fixed-size token windows.

    Parameters mirror the historical 512/64 defaults and are configurable via
    ``GABRIEL_CHUNK_SIZE`` / ``GABRIEL_CHUNK_OVERLAP`` or per instance.
    """

    chunk_size: int = field(default_factory=lambda: DEFAULT_CHUNK_SIZE)
    chunk_overlap: int = field(default_factory=lambda: DEFAULT_CHUNK_OVERLAP)

    def __post_init__(self) -> None:
        if self.chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap must be >= 0")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")

    def split(self, text: str) -> list[Chunk]:
        """Split *text* into overlapping :class:`Chunk` windows.

        Empty / whitespace-only input yields no chunks.
        """
        tokens = text.split()
        if not tokens:
            return []

        step = max(1, self.chunk_size - self.chunk_overlap)
        chunks: list[Chunk] = []
        start = 0
        index = 0
        while start < len(tokens):
            end = min(start + self.chunk_size, len(tokens))
            window = tokens[start:end]
            chunks.append(
                Chunk(index=index, text=" ".join(window), token_count=len(window))
            )
            if end == len(tokens):
                break
            start += step
            index += 1
        return chunks
