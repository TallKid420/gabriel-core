"""Memory backend implementations (ADR-014: Polyglot Memory Fabric).

Backends implement the MemoryAccessInterface (MAI) contract. The
ScopedMemoryClient routes through PEEL, then delegates to a backend.

Available backends
------------------
PostgresMemoryBackend : Durable PostgreSQL backend with pgvector semantic search.
"""

from gabriel.memory.backends.postgres import PostgresMemoryBackend

__all__ = ["PostgresMemoryBackend"]
