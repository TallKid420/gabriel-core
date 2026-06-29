from abc import ABC, abstractmethod
from typing import List, Optional

from gabriel.memory.models import MemoryEntry, MemoryLayer

class MemoryAccessInterface(ABC):
    @abstractmethod
    async def store(self, entry: MemoryEntry) -> str:
        """Stores a memory entry and returns its ID."""
        pass

    @abstractmethod
    async def retrieve(
        self,
        layer: MemoryLayer,
        query: Optional[str] = None,
        limit: int = 10
    ) -> List[MemoryEntry]:
        """Retrieves memory from a specific layer."""
        pass

    @abstractmethod
    async def forget(self, memory_id: str) -> None:
        """Removes a specific memory."""
        pass