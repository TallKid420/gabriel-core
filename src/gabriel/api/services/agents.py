"""Agent listing service for the API gateway.

This module keeps the agents index endpoint thin:
router -> service -> repository/mock projection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gabriel.identity.principal import Principal
from gabriel.api.schema import AgentSummary


class AgentRepository:
    """Repository over the gateway's in-memory resource projection."""

    def __init__(self, resource_projection) -> None:
        self._resource_projection = resource_projection

    def list_available_agents(self, organization_id: str) -> list[dict[str, Any]]:
        return self._resource_projection.list_resources(
            organization_id=organization_id,
            resource_type="agent",
        )


class AgentService:
    """Application service for agent listing and future policy-backed access checks."""

    def __init__(self, repository: AgentRepository) -> None:
        self._repository = repository

    def list_available_agents(self, principal: Principal) -> list[AgentSummary]:
        resources = self._repository.list_available_agents(principal.organization_id)
        return [_resource_to_summary(resource) for resource in resources]


def _resource_to_summary(resource: dict[str, Any]) -> AgentSummary:
    attributes = resource.get("attributes") or {}
    if not isinstance(attributes, dict):
        attributes = {}

    config = attributes.get("config") or {}
    if not isinstance(config, dict):
        config = {}

    status = str(resource.get("state") or "active")
    enabled = status == "active"

    return AgentSummary(
        id=str(resource["grn"]),
        name=str(attributes.get("name") or resource.get("name") or ""),
        description=attributes.get("description") or config.get("description"),
        status=status,
        icon=attributes.get("icon") or config.get("icon"),
        category=attributes.get("category") or config.get("category"),
        provider=attributes.get("provider") or config.get("provider") or config.get("llm_provider"),
        model=attributes.get("model") or config.get("model") or config.get("llm_model"),
        enabled=enabled,
    )