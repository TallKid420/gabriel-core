"""Gabriel memory subsystem (ADR-012, ADR-014).

Exports the Memory Access Interface, domain models, the scoped client,
and available backend implementations.
"""

from gabriel.memory.backends.postgres import PostgresMemoryBackend
from gabriel.memory.client import ScopedMemoryClient
from gabriel.memory.contract import MemoryAccessInterface
from gabriel.memory.models import MemoryEntry, MemoryLayer
from gabriel.memory.orm import MemoryEntryORM
from gabriel.memory.providers.local import LocalMemoryProvider

__all__ = [
    # Contract
    "MemoryAccessInterface",
    # Domain models
    "MemoryEntry",
    "MemoryLayer",
    # ORM
    "MemoryEntryORM",
    # Client
    "ScopedMemoryClient",
    # Backends
    "LocalMemoryProvider",
    "PostgresMemoryBackend",
]
