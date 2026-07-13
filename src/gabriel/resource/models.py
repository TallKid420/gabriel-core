from datetime import datetime, timezone
from typing import Any
from enum import Enum

from pydantic import BaseModel, Field

from gabriel.resource.grn import GRN


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ResourceState(str, Enum):
    DRAFT      = "draft"
    ACTIVE     = "active"
    SUSPENDED  = "suspended"
    DEPRECATED = "deprecated"
    DELETED    = "deleted"

class ResourceType(str, Enum):
    ORGANIZATION = "organization"
    USER         = "user"
    AGENT        = "agent"
    TOOL         = "tool"
    POLICY       = "policy"
    MEMORY       = "memory"
    MODEL        = "model"
    SOLUTION     = "solution"
    WORKFLOW     = "workflow"
    CONNECTOR    = "connector"
    DOCUMENT     = "document"
    FILE         = "file"
    CONVERSATION = "conversation"
    MESSAGE      = "message"
    NOTIFICATION = "notification"

class Resource(BaseModel):
    grn: GRN
    org_id: str
    resource_type: ResourceType
    state: ResourceState = ResourceState.DRAFT
    version: int = 1
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    created_by: str
    updated_by: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)

    model_config = {"frozen": True}

    def with_state(self, new_state: ResourceState, updated_by: str) -> "Resource":
        """ Returns a new Resource with updated state, updated_at, updated_by"""
        return self.model_copy(
            update={
                "state": new_state,
                "updated_at": utcnow(),
                "updated_by": updated_by,
            }
        )

    def with_metadata(self, key: str, value: Any) -> "Resource":
        """ Returns a new Resource with updated metadata"""
        return self.model_copy(
            update={
                "metadata": {**self.metadata, key: value},
                "updated_at": utcnow(),
            }
        )