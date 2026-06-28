"""Runtime execution configuration used by runtime adapters."""

from pydantic import BaseModel, Field


class RuntimeConfiguration(BaseModel):
    runtime: str
    timeout_seconds: int = 60
    max_iterations: int = 10
    temperature: float = 0.0
    max_tokens: int = 4096

    model_config = {"frozen": True}