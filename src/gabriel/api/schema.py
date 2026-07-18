"""Pydantic request/response schemas for the Gabriel API gateway."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from gabriel.agent.management import AgentStatus

from pydantic import BaseModel, ConfigDict, Field
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------
class OkResponse(BaseModel):
    ok: bool = True
    detail: Optional[str] = None


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Health status of the service.")


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------
class ResourceCreateRequest(BaseModel):
    resource_type: str = Field(..., examples=["agent"])
    resource_id: str | None = None
    version: int = 1
    attributes: dict[str, Any] = Field(default_factory=dict)


class ResourceUpdateRequest(BaseModel):
    attributes: dict[str, Any] = Field(default_factory=dict)


class ResourceResponse(BaseModel):
    grn: str
    resource_type: str | None = None
    state: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class ResourceDeleteResponse(BaseModel):
    deleted: bool
    grn: str


class ResourceListResponse(BaseModel):
    items: list[ResourceResponse]


# ---------------------------------------------------------------------------
# Agent Specifications
# ---------------------------------------------------------------------------

class AgentSpecTemplate(BaseModel):
    templates: list[dict[str, Any]] = Field(default_factory=list)


class AgentSpecResponse(BaseModel):
    specs: list[str] = Field(default_factory=list)

# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentSummary:
    """Summary view of an agent suitable for list pages."""

    id: str
    name: str
    description: str | None
    status: str
    icon: str | None
    category: str | None
    provider: str | None
    model: str | None
    enabled: bool

class AgentSummaryResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    status: str
    icon: str | None = None
    category: str | None = None
    provider: str | None = None
    model: str | None = None
    enabled: bool


class AgentExecuteRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)


class AgentStateResponse(BaseModel):
    grn: str
    status: str
    last_event: str


class AgentCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    system_prompt: str = ""
    model_settings: dict[str, Any] | None = Field(default=None, alias="model_config")
    allowed_tools: list[str] | None = None
    disabled_tools: list[str] | None = None
    knowledge_sources: list[str] | None = None
    document_collections: list[str] | None = None
    status: str = AgentStatus.ACTIVE.value
    runtime: str = "default"
    metadata: dict[str, Any] | None = None
    labels: dict[str, str] | None = None


class AgentUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    system_prompt: str | None = None
    model_settings: dict[str, Any] | None = Field(default=None, alias="model_config")
    allowed_tools: list[str] | None = None
    disabled_tools: list[str] | None = None
    knowledge_sources: list[str] | None = None
    document_collections: list[str] | None = None
    status: str | None = None
    metadata: dict[str, Any] | None = None


class AgentListResponse(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    total: int = Field(description="Total number of agents available.")
    limit: int = Field(description="Maximum number of agents to return.")
    offset: int = Field(description="Number of agents to skip.")


class AgentDeleteResponse(BaseModel):
    deleted: bool
    grn: str


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------
class MemoryCreateRequest(BaseModel):
    content: Any
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryListResponse(BaseModel):
    items: list[dict[str, Any]]


class MemoryDeleteResponse(BaseModel):
    deleted: bool
    id: str


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
class EventResponse(BaseModel):
    id: str
    type: str
    principal_id: str
    organization_id: str
    resource_grn: str | None = None
    occurred_at: datetime
    correlation_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EventListResponse(BaseModel):
    items: list[EventResponse]


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------
class DocumentResponse(BaseModel):
    grn: str
    resource_type: str = "document"
    state: str
    filename: str
    media_type: str | None = None
    source_uri: str | None = None
    content_hash: str | None = None
    content_pointer: str | None = None
    byte_size: int | None = None
    event_id: str
    event_type: str

class DocumentAllowedTypesResponse(BaseModel):
    allowed_types: set[str] = Field(
        default_factory=set,
        description="List of document types that can be uploaded to this tenant."
    )

# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChatSummary:
    id: str
    title: str | None
    agentGRN: str | None
    createdAt: datetime | str | None
    updatedAt: datetime | str | None
    messageCount: int | None
    lastMessagePreview: str | None

class ChatSummaryResponse(BaseModel):
    id: str | None = None
    title: str | None = None
    agentGRN: str | None = None
    createdAt: datetime | str |None = None
    updatedAt: datetime | str | None = None
    messageCount: int | None = None
    lastMessagePreview: str | None = None

class ChatCreateRequest(BaseModel):
    title: str | None = Field(
        default=None,
        max_length=200,
        description="Optional user-defined title."
    )

    agentGRN: str | None = Field(
        default=None,
        description="Default agent assigned to the conversation."
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Application-defined metadata."
    )

    # project_grn: str | None = Field(
    #     default=None,
    #     description="Optional project this chat belongs to."
    # )

    # resource_grns: list[str] = Field(
    #     default_factory=list,
    #     description="Resources initially attached to the conversation."
    # )

# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

class Notification(BaseModel):
    grn: str
    level: str
    # organization: str
    # recipient: str
    # actor: str | None
    title: str
    body: str
    # source_event: str | None
    # workflow: str | None
    created_at: datetime
    read: bool = False