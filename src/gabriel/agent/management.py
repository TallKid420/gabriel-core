"""Agent management service (Phase 2 — Core Business Logic).

A management-shaped facade over the persisted Agent resource slice
(Model → ORM → Mapper → Repository) that exposes agents the way operators
think about them:

    name, description, system_prompt,
    model_config (provider / model / temperature / max_tokens),
    allowed_tools, knowledge_sources, status (active | inactive | draft)

Internally these fields live on the declarative :class:`AgentSpecification`
(Phase 4 contract) so the runtime/deployment machinery keeps working
unchanged. Status maps onto the Resource lifecycle:

    active   → ResourceState.ACTIVE,    enabled=True
    inactive → ResourceState.SUSPENDED, enabled=False
    draft    → ResourceState.DRAFT,     enabled=False
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from gabriel.agent.mappers import domain_to_orm, orm_to_domain
from gabriel.agent.models import Agent
from gabriel.agent.repository import AgentRepository
from gabriel.agent.runtime_config import RuntimeConfiguration
from gabriel.agent.specification import AgentSpecification
from gabriel.events.event import Event
from gabriel.events.repository import EventRepository
from gabriel.resource.exceptions import DuplicateResourceError
from gabriel.resource.grn import GRN
from gabriel.resource.models import ResourceState


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DRAFT = "draft"


_STATUS_TO_STATE: dict[AgentStatus, tuple[ResourceState, bool]] = {
    AgentStatus.ACTIVE: (ResourceState.ACTIVE, True),
    AgentStatus.INACTIVE: (ResourceState.SUSPENDED, False),
    AgentStatus.DRAFT: (ResourceState.DRAFT, False),
}

_STATE_TO_STATUS: dict[ResourceState, AgentStatus] = {
    ResourceState.ACTIVE: AgentStatus.ACTIVE,
    ResourceState.SUSPENDED: AgentStatus.INACTIVE,
    ResourceState.DRAFT: AgentStatus.DRAFT,
    # Anything else (deprecated/deleted) presents as inactive.
    ResourceState.DEPRECATED: AgentStatus.INACTIVE,
    ResourceState.DELETED: AgentStatus.INACTIVE,
}


class ModelConfig(BaseModel):
    """LLM configuration for an agent."""

    provider: str = ""
    model: str = ""
    temperature: float = 0.0
    max_tokens: int = 4096
    extra: dict[str, Any] = Field(default_factory=dict)


def _normalize_status(status: AgentStatus | str) -> AgentStatus:
    return status if isinstance(status, AgentStatus) else AgentStatus(status)


def agent_public_view(agent: Agent) -> dict[str, Any]:
    """Management-shaped serializable representation of an Agent resource."""
    spec = agent.specification
    runtime_config = spec.effective_runtime_config()
    return {
        "grn": str(agent.grn),
        "org_id": agent.org_id,
        "name": spec.name,
        "description": spec.description,
        "system_prompt": spec.system_prompt,
        "model_config": {
            "provider": spec.provider,
            "model": spec.model,
            "temperature": runtime_config.temperature,
            "max_tokens": runtime_config.max_tokens,
        },
        "allowed_tools": spec.tools,
        "knowledge_sources": spec.knowledge_sources,
        "status": _STATE_TO_STATUS.get(agent.state, AgentStatus.INACTIVE).value,
        "enabled": agent.enabled,
        "state": agent.state.value,
        "version": agent.version,
        "created_at": agent.created_at.isoformat(),
        "updated_at": agent.updated_at.isoformat(),
        "created_by": agent.created_by,
        "metadata": agent.metadata,
        "labels": agent.labels,
    }


class AgentManagementService:
    """Business logic for managing Agent resources (org-scoped)."""

    def __init__(self, repository: AgentRepository, event_repo: EventRepository | None = None):
        self.repo = repository
        self.event_repo = event_repo

    async def _append_event(
        self,
        event_type: str,
        *,
        principal_id: str,
        org_id: str,
        grn_str: str,
        operation: str,
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        if self.event_repo is None:
            return
        await self.event_repo.append(
            Event(
                type=event_type,
                principal_id=principal_id,
                organization_id=org_id,
                resource_grn=grn_str,
                correlation_id=correlation_id,
                payload={"resource_type": "agent", "grn": grn_str, **(payload or {})},
                metadata={"service": "AgentManagementService", "operation": operation},
            )
        )
        await self.repo.session.commit()

    async def create_agent(
        self,
        org_id: str,
        name: str,
        *,
        created_by: str,
        description: str = "",
        system_prompt: str = "",
        model_config: ModelConfig | dict[str, Any] | None = None,
        allowed_tools: list[str] | None = None,
        knowledge_sources: list[str] | None = None,
        status: AgentStatus | str = AgentStatus.ACTIVE,
        runtime: str = "default",
        metadata: dict[str, Any] | None = None,
        labels: dict[str, str] | None = None,
        correlation_id: str | None = None,
    ) -> Agent:
        """Create an agent resource from management-shaped fields."""
        config = (
            model_config
            if isinstance(model_config, ModelConfig)
            else ModelConfig(**(model_config or {}))
        )
        normalized_status = _normalize_status(status)
        state, enabled = _STATUS_TO_STATE[normalized_status]

        specification = AgentSpecification(
            name=name,
            description=description,
            runtime=runtime,
            model=config.model,
            provider=config.provider,
            system_prompt=system_prompt,
            tools=allowed_tools or [],
            knowledge_sources=knowledge_sources or [],
            runtime_config=RuntimeConfiguration(
                runtime=runtime,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            ),
        )

        grn = GRN.generate(org_id, "agent")
        agent = Agent.create(
            grn=grn,
            org_id=org_id,
            created_by=created_by,
            specification=specification,
            enabled=enabled,
            metadata=metadata or {},
            labels=labels or {},
        ).model_copy(update={"state": state})

        try:
            persisted = await self.repo.create(domain_to_orm(agent))
        except IntegrityError as exc:
            raise DuplicateResourceError(
                f"Agent with GRN '{grn}' already exists."
            ) from exc
        await self._append_event(
            "resource_created",
            principal_id=created_by,
            org_id=org_id,
            grn_str=str(grn),
            operation="create_agent",
            payload={"name": name, "status": normalized_status.value},
            correlation_id=correlation_id,
        )
        return orm_to_domain(persisted)

    async def get_agent(self, grn_str: str, org_id: str | None = None) -> Agent:
        agent = orm_to_domain(await self.repo.get_by_grn(grn_str))
        if org_id is not None and agent.org_id != org_id:
            # Tenant isolation: never leak other orgs' agents.
            from gabriel.resource.exceptions import ResourceNotFoundError

            raise ResourceNotFoundError(f"Agent {grn_str} not found")
        return agent

    async def list_agents(
        self, org_id: str, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[Agent], int]:
        """Paginated org-scoped listing; returns (items, total)."""
        orms, total = await self.repo.list_for_org_paginated(
            org_id, limit=limit, offset=offset
        )
        return [orm_to_domain(orm) for orm in orms], total

    async def update_agent(
        self,
        grn_str: str,
        *,
        updated_by: str,
        org_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        system_prompt: str | None = None,
        model_config: ModelConfig | dict[str, Any] | None = None,
        allowed_tools: list[str] | None = None,
        knowledge_sources: list[str] | None = None,
        status: AgentStatus | str | None = None,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> Agent:
        """Update management fields; bumps the resource version."""
        existing = await self.get_agent(grn_str, org_id=org_id)
        spec = existing.specification

        spec_updates: dict[str, Any] = {}
        if name is not None:
            spec_updates["name"] = name
        if description is not None:
            spec_updates["description"] = description
        if system_prompt is not None:
            spec_updates["system_prompt"] = system_prompt
        if allowed_tools is not None:
            spec_updates["tools"] = allowed_tools
        if knowledge_sources is not None:
            spec_updates["knowledge_sources"] = knowledge_sources
        if model_config is not None:
            config = (
                model_config
                if isinstance(model_config, ModelConfig)
                else ModelConfig(**model_config)
            )
            spec_updates["model"] = config.model or spec.model
            spec_updates["provider"] = config.provider or spec.provider
            current_runtime = spec.effective_runtime_config()
            spec_updates["runtime_config"] = RuntimeConfiguration(
                runtime=current_runtime.runtime,
                timeout_seconds=current_runtime.timeout_seconds,
                max_iterations=current_runtime.max_iterations,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            )
        new_spec = spec.model_copy(update=spec_updates) if spec_updates else spec

        resource_updates: dict[str, Any] = {
            "specification": new_spec,
            "updated_by": updated_by,
            "updated_at": utcnow(),
            "version": existing.version + 1,
        }
        if status is not None:
            normalized_status = _normalize_status(status)
            state, enabled = _STATUS_TO_STATE[normalized_status]
            resource_updates["state"] = state
            resource_updates["enabled"] = enabled
        if metadata is not None:
            resource_updates["metadata"] = {**existing.metadata, **metadata}

        updated = existing.model_copy(update=resource_updates)
        persisted = await self.repo.update(domain_to_orm(updated))
        await self._append_event(
            "resource_updated",
            principal_id=updated_by,
            org_id=existing.org_id,
            grn_str=grn_str,
            operation="update_agent",
            payload={"name": new_spec.name},
            correlation_id=correlation_id,
        )
        return orm_to_domain(persisted)

    async def delete_agent(
        self,
        grn_str: str,
        *,
        deleted_by: str,
        org_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        existing = await self.get_agent(grn_str, org_id=org_id)
        await self.repo.delete(grn_str)
        await self._append_event(
            "resource_deleted",
            principal_id=deleted_by,
            org_id=existing.org_id,
            grn_str=grn_str,
            operation="delete_agent",
            correlation_id=correlation_id,
        )
