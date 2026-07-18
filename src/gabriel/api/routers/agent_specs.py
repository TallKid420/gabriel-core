"""Agent-specification HTTP API (core-owned).

These endpoints expose gabriel-core's migrated agent specification system over
HTTP so that the ``gabriel-desktop`` gateway can consume them **without
importing gabriel-core**. All agent-spec business logic lives in
:class:`gabriel.api.services.agent_specs.AgentSpecService`.

Routes (mounted under ``/api/v1``):

    GET    /agent-specs/templates        list migrated template descriptors
    POST   /agent-specs/instantiate      build a spec from a template + overrides
    GET    /agent-specs                  list persisted spec names
    POST   /agent-specs                  build + persist a spec
    GET    /agent-specs/{name}           load a persisted spec
    DELETE /agent-specs/{name}           delete a persisted spec
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from gabriel.agent.exceptions import AgentValidationError
from gabriel.api.schema import (
    AgentSpecTemplate,
)
from gabriel.api.services.agent_specs import (
    AgentSpecService,
    SpecificationNotFoundError,
    get_agent_spec_service,
)

router = APIRouter(prefix="/agent-specs", tags=["Agent Specifications"])


class InstantiateRequest(BaseModel):
    """Request to build a spec from a template."""

    template: str
    name: str | None = None
    model: str | None = None
    system_prompt: str | None = Field(default=None, alias="systemPrompt")
    provider: str | None = None
    extra_tools: list[str] | None = Field(default=None, alias="extraTools")
    metadata: dict[str, str] | None = None

    model_config = {"populate_by_name": True}

    def to_overrides(self) -> dict[str, Any]:
        overrides: dict[str, Any] = {}
        for key in ("name", "model", "provider", "metadata"):
            value = getattr(self, key)
            if value is not None:
                overrides[key] = value
        if self.system_prompt is not None:
            overrides["system_prompt"] = self.system_prompt
        if self.extra_tools is not None:
            overrides["extra_tools"] = self.extra_tools
        return overrides


class SaveRequest(InstantiateRequest):
    """Build-and-persist request (same shape as instantiate)."""


def _build_spec(service: AgentSpecService, req: InstantiateRequest):
    try:
        return service.instantiate(req.template, **req.to_overrides())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (AgentValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/templates", response_model=AgentSpecTemplate)
async def list_templates_endpoint(
    service: AgentSpecService = Depends(get_agent_spec_service),
) -> AgentSpecTemplate:
    return AgentSpecTemplate(templates=service.describe_templates())


@router.post("/instantiate")
async def instantiate_endpoint(
    req: InstantiateRequest,
    service: AgentSpecService = Depends(get_agent_spec_service),
) -> dict[str, Any]:
    spec = _build_spec(service, req)
    return service.spec_payload(spec)


@router.get("")
async def list_specs_endpoint(
    service: AgentSpecService = Depends(get_agent_spec_service),
) -> dict[str, list[str]]:
    return {"specs": service.list_saved()}


@router.post("", status_code=status.HTTP_201_CREATED)
async def save_spec_endpoint(
    req: SaveRequest,
    service: AgentSpecService = Depends(get_agent_spec_service),
) -> dict[str, Any]:
    spec = _build_spec(service, req)
    path = service.save(spec)
    payload = service.spec_payload(spec)
    payload["path"] = path
    return payload


@router.get("/{name}")
async def load_spec_endpoint(
    name: str,
    service: AgentSpecService = Depends(get_agent_spec_service),
) -> dict[str, Any]:
    try:
        spec = service.load(name)
    except SpecificationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return service.spec_payload(spec)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_spec_endpoint(
    name: str,
    service: AgentSpecService = Depends(get_agent_spec_service),
) -> None:
    try:
        service.delete(name)
    except SpecificationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
