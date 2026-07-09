from typing import Optional

from gabriel.memory.contract import MemoryAccessInterface
from gabriel.memory.models import MemoryEntry, MemoryLayer

class LocalMemoryProvider(MemoryAccessInterface):
    """In-process memory provider for testing and development.

    Stores entries in a plain dict — no persistence, no vector search.
    The :meth:`search` method falls back to substring matching.
    """

    def __init__(self):
        self._entries: dict[str, MemoryEntry] = {}
        self._order: list[str] = []
        self._next_id = 1

    async def store(self, entry: MemoryEntry) -> str:
        memory_id = str(self._next_id)
        self._next_id += 1
        self._entries[memory_id] = entry
        self._order.append(memory_id)
        return memory_id
    
    async def retrieve(
        self,
        layer: MemoryLayer,
        query: Optional[str] = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        matches: list[MemoryEntry] = []
        for memory_id in self._order:
            entry = self._entries.get(memory_id)
            if entry is None or entry.layer != layer:
                continue
            if query is not None and query not in str(entry.content):
                continue
            matches.append(entry)
            if len(matches) >= limit:
                break
        return matches
    
    async def search(
        self,
        query: str,
        layer: Optional[MemoryLayer] = None,
        limit: int = 10
    ) -> list[MemoryEntry]:
            """Keyword fallback — no vector search in local provider."""
            matches: list[MemoryEntry] = []
            for memory_id in self._order:
                entry = self._entries.get(memory_id)
                if entry is None:
                    continue
                if layer is not None and entry.layer != layer:
                    continue
                if query.lower() in str(entry.content).lower():
                    matches.append(entry)
                if len(matches) >= limit:
                    break
            return matches
    
    async def forget(self, memory_id: str) -> None:
        if memory_id in self._entries:
            del self._entries[memory_id]
        self._order = [eid for eid in self._order if eid != memory_id]