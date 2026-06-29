"""Gabriel memory subsystem exports."""

from gabriel.memory.client import ScopedMemoryClient
from gabriel.memory.contract import MemoryAccessInterface
from gabriel.memory.models import MemoryEntry, MemoryLayer
from gabriel.memory.providers.local import LocalMemoryProvider

__all__ = [
    "MemoryAccessInterface",
    "MemoryEntry",
    "MemoryLayer",
    "ScopedMemoryClient",
    "LocalMemoryProvider",
]
