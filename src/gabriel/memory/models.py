from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

class MemoryLayer(str, Enum):
    SHORT_TERM = "short_term" # Context window / working memory
    LONG_TERM = "long_term" # Knowledge base / Vector store
    EPISODIC = "episodic" # Past experiences / logs

class MemoryEntry(BaseModel):
    layer: MemoryLayer
    content: Any
    importance: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)