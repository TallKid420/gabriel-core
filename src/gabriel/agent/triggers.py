"""Event-based trigger declarations for agent deployment."""

from pydantic import BaseModel, Field, field_validator


class Trigger(BaseModel):
    """Declares an event type that should trigger the agent."""

    event_type: str
    filter: dict[str, str] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("event_type must not be empty")
        return value