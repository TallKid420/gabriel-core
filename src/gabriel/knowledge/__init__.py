"""Knowledge slice (Phase 4): chunking, embeddings, vector search, RAG.

Vertical slice for GABRIEL's document-grounded retrieval:

- ``chunking``          — deterministic text chunking (size/overlap).
- ``embeddings``        — hot-swappable embedding providers (Ollama default).
- ``chunk_orm``         — ``document_chunks`` table (text + vectors).
- ``vector_store``      — cosine-similarity search (pgvector / fallback).
- ``source_*``          — KnowledgeSource resource (document collections).
- ``retrieval``         — query → context blocks for the gateway runtime.
"""
from gabriel.knowledge.chunking import Chunk, TextChunker
from gabriel.knowledge.embeddings import (
    EmbeddingProvider,
    EmbeddingProviderRegistry,
    OllamaEmbeddingProvider,
    register_default_embedding_providers,
)
from gabriel.knowledge.retrieval import KnowledgeRetriever
from gabriel.knowledge.source_models import KnowledgeSource, KnowledgeSourceStatus
from gabriel.knowledge.vector_store import ChunkSearchResult, ChunkVectorStore

__all__ = [
    "Chunk",
    "TextChunker",
    "EmbeddingProvider",
    "EmbeddingProviderRegistry",
    "OllamaEmbeddingProvider",
    "register_default_embedding_providers",
    "KnowledgeRetriever",
    "KnowledgeSource",
    "KnowledgeSourceStatus",
    "ChunkSearchResult",
    "ChunkVectorStore",
]
