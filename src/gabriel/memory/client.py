from gabriel.runtime.context import ExecutionContext
from gabriel.memory.contract import MemoryAccessInterface
from gabriel.memory.models import MemoryEntry, MemoryLayer

from typing import Any

class ScopedMemoryClient:
    def __init__(self, context: ExecutionContext, provider: MemoryAccessInterface):
        self.context = context
        self.provider = provider

    async def write(self, content: Any, layer: MemoryLayer = MemoryLayer.SHORT_TERM) -> str:
        # Automatically wrap the content with context metadata
        entry = MemoryEntry(
            content=content,
            layer=layer,
            metadata={
                "principal": str(self.context.principal.id),
                "org": self.context.organization,
            },
        )
        return await self.provider.store(entry)

    async def read(
        self,
        layer: MemoryLayer = MemoryLayer.SHORT_TERM,
        query: str | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        return await self.provider.retrieve(layer=layer, query=query, limit=limit)

    async def forget(self, memory_id: str) -> None:
        await self.provider.forget(memory_id)