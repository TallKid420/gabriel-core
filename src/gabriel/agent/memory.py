"""Memory requirement declarations for agent specifications."""

from pydantic import BaseModel, Field


class MemoryRequirements(BaseModel):
    """Declares memory layers and retention policy for an agent."""

    read_layers: list[str] = Field(default_factory=list)
    write_layers: list[str] = Field(default_factory=list)
    retention: str = "session"

    model_config = {"frozen": True}