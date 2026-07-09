"""Agent-specification application service (core-owned).

This service holds all agent-specification business logic. It used to live in
the ``gabriel-desktop`` gateway, but Phase 4 wiring moves it into gabriel-core
so the desktop layer can consume it purely over HTTP (see
``gabriel.api.routers.agent_specs``). The desktop gateway is a Backend-For-
Frontend and must not import gabriel-core; it talks to these endpoints.

Responsibilities
----------------
* Expose the migrated template library (chat/engineer/researcher/daemon/server).
* Instantiate a template into a concrete :class:`AgentSpecification`, applying
  browser-supplied overrides (name, model, system prompt, …), validated.
* Resolve wildcard tool GRNs to concrete, org-scoped tool GRNs.
* Persist / load specifications through :class:`AgentSpecificationStore`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gabriel.agent import (
    AgentSpecification,
    AgentSpecificationStore,
    AgentValidator,
    build_specification,
    get_template,
    list_templates,
    template_vocabulary,
)
from gabriel.agent.store import SpecificationNotFoundError

__all__ = ["AgentSpecService", "SpecificationNotFoundError", "get_agent_spec_service"]

_SPECS_DIR_ENV = "GABRIEL_AGENT_SPECS_DIR"
_ORG_ID_ENV = "GABRIEL_DEFAULT_ORG_ID"


@dataclass
class AgentSpecService:
    """Core service that owns the agent-specification workflow.

    Args:
        specs_dir: Directory backing the :class:`AgentSpecificationStore`.
        org_id: Organization used to resolve wildcard tool bindings to GRNs.
    """

    specs_dir: str
    org_id: str = "acme"

    def __post_init__(self) -> None:
        self._store = AgentSpecificationStore(self.specs_dir)
        vocab = template_vocabulary()
        self._validator = AgentValidator(
            runtimes=vocab["runtimes"],
            tools=vocab["tools"],
            capabilities=vocab["capabilities"],
            memory_layers=vocab["memory_layers"],
            models=vocab["models"],
        )

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------
    def list_template_keys(self) -> list[str]:
        """Return the available template keys (legacy agent types)."""
        return list_templates()

    def describe_templates(self) -> list[dict[str, Any]]:
        """Return browser-friendly descriptors for every template."""
        descriptors: list[dict[str, Any]] = []
        for key in list_templates():
            template = get_template(key)
            spec = template.build()
            descriptors.append(
                {
                    "key": template.key,
                    "legacyClass": template.legacy_class,
                    "name": spec.name,
                    "description": spec.description,
                    "model": spec.model,
                    "provider": spec.provider,
                    "runtime": spec.runtime,
                    "capabilities": spec.capabilities,
                    "tools": spec.tools,
                    "memoryLayers": spec.memory_layers,
                    "triggers": [t.event_type for t in spec.normalized_triggers()],
                }
            )
        return descriptors

    # ------------------------------------------------------------------
    # Instantiate + validate
    # ------------------------------------------------------------------
    def instantiate(self, template_key: str, **overrides: Any) -> AgentSpecification:
        """Build a concrete specification from a template + overrides, validated."""
        spec = build_specification(template_key, **overrides)
        # Validator checks tool *names* rather than GRN bindings.
        self._validator.validate(spec.model_copy(update={"tools": spec.tool_names()}))
        return spec

    def resolve_tool_grns(self, spec: AgentSpecification, version: int = 1) -> list[str]:
        """Resolve a spec's (wildcard) tool bindings to concrete org-scoped GRNs."""
        return spec.resolved_tools(self.org_id, version)

    def spec_payload(self, spec: AgentSpecification) -> dict[str, Any]:
        """Serialize a spec for HTTP, adding resolved tool GRNs."""
        data = spec.model_dump(mode="json")
        data["resolvedTools"] = self.resolve_tool_grns(spec)
        return data

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save(self, spec: AgentSpecification, *, name: str | None = None) -> str:
        """Persist *spec*; return the on-disk path as a string."""
        return str(self._store.save(spec, name=name))

    def load(self, name: str) -> AgentSpecification:
        """Load a persisted specification by name."""
        return self._store.load(name)

    def list_saved(self) -> list[str]:
        """List persisted specification names."""
        return self._store.list()

    def delete(self, name: str) -> None:
        """Delete a persisted specification."""
        self._store.delete(name)

    def seed_templates(self) -> list[str]:
        """Persist every template spec into the store; return names written."""
        names: list[str] = []
        for key in list_templates():
            spec = build_specification(key)
            self._store.save(spec)
            names.append(spec.name)
        return names


def get_agent_spec_service() -> AgentSpecService:
    """Construct a service from environment configuration.

    Reads env each call so tests can point it at a temp directory:
      * ``GABRIEL_AGENT_SPECS_DIR`` — spec store location.
      * ``GABRIEL_DEFAULT_ORG_ID`` — org used for GRN resolution.
    """
    specs_dir = os.environ.get(
        _SPECS_DIR_ENV, str(Path.cwd() / ".gabriel" / "agent-specs")
    )
    org_id = os.environ.get(_ORG_ID_ENV, "acme")
    return AgentSpecService(specs_dir=specs_dir, org_id=org_id)
