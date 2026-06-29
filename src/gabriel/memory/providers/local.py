from gabriel.memory.contract import MemoryAccessInterface
from gabriel.memory.models import MemoryEntry, MemoryLayer

class LocalMemoryProvider(MemoryAccessInterface):
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
        query: str | None = None,
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
    
    async def forget(self, memory_id: str) -> None:
        if memory_id in self._entries:
            del self._entries[memory_id]
        self._order = [existing_id for existing_id in self._order if existing_id != memory_id]