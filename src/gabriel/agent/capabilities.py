"""Agent capability declaration models."""

from pydantic import BaseModel, Field


class AgentCapabilities(BaseModel):
    """Requested capabilities. PEEL determines what is granted."""

    requested: set[str] = Field(default_factory=set)

    model_config = {"frozen": True}