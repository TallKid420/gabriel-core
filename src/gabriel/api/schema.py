"""Pydantic request/response schemas for the Gabriel API gateway."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


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


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------
class AgentCreateRequest(BaseModel):
    name: str
    runtime: str = "mock"
    config: dict[str, Any] = Field(default_factory=dict)


class AgentExecuteRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)


class AgentStateResponse(BaseModel):
    grn: str
    status: str
    last_event: str


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