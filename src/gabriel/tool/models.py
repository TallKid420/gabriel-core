"""Tool resource models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from gabriel.resource.grn import GRN
from gabriel.resource.models import Resource, ResourceState, ResourceType

class ToolCategory(str, Enum):
    """Broad category a tool belongs to.

    Drives UI grouping, documentation, and future capability-based filtering.
    """

    MATH = "math"
    TEXT = "text"
    TIME = "time"
    RANDOM = "random"
    UTILITY = "utility"
    FILE = "file"
    EMAIL = "email"
    CALENDAR = "calendar"
    SEARCH = "search"
    SYSTEM = "system"
    CUSTOM = "custom"


class ExecutionRuntime(str, Enum):
    """Where a tool declares it executes (V1: declaration only).

    Runtime *routing* is future work — no execution engine consumes this yet.
    Declaring it now lets tools be authored against the target topology
    without a later schema migration (Architecture Spec §Runtime Preparation).

    LOCAL      — in-process, inside gabriel-core (all V1 built-ins).
    ENTERPRISE — customer-hosted runtime inside the org's network boundary.
    CLOUD      — Gabriel-managed cloud runtime.
    EDGE       — device/edge runtime (future).
    """

    LOCAL = "local"
    ENTERPRISE = "enterprise"
    CLOUD = "cloud"
    EDGE = "edge"


class SafetyLevel(int, Enum):
    """Risk classification for a tool.

    Used by the ToolExecutor to decide whether human confirmation is required
    before the tool may be invoked.

    SAFE (0)                — stateless, read-only, no external side-effects.
    REQUIRES_CONFIRMATION (1) — writes external state or touches user data;
                                the calling agent must obtain explicit approval
                                before the executor will dispatch.
    RESTRICTED (2)          — disabled by default; requires an explicit policy
                                ALLOW statement from an org admin.
    """

    SAFE = 0
    REQUIRES_CONFIRMATION = 1
    RESTRICTED = 2

class Tool(Resource):
    """Declarative tool resource.

    A Tool is a *registered capability* that an Agent may invoke through the
    ToolExecutor.  It is NOT the executable itself — execution is resolved at
    runtime via ``runtime_binding`` which maps to a registered callable (for
    function-type tools) or an integration handler (for external tools).

    Fields
    ------
    name                : Unique slug within the org (e.g. "calculate").
    description         : Human-readable purpose shown in tool-picker UIs.
    category            : Broad grouping via :class:`ToolCategory`.
    input_schema        : JSON Schema dict for validating invocation arguments.
    output_schema       : JSON Schema dict for validating tool return values.
    safety_level        : Risk classification via :class:`SafetyLevel`.
    required_capabilities : Capability strings checked by PEEL before dispatch.
    runtime_binding     : Dot-path key used by the FunctionRegistry / executor
                          to locate the callable.  Examples:
                          - ``"math.calculate"``         (pure function)
                          - ``"file.find_file"``         (org-scoped file tool)
                          - ``"integration.gmail.send_email"`` (integration)
    execution_runtime   : Declared execution location (:class:`ExecutionRuntime`).
                          V1 is declaration-only; routing comes later.
    enabled             : Org-level kill switch. A disabled tool is excluded
                          from chat-runtime tool exposure regardless of what
                          any agent specification declares.
    configuration       : Free-form, tool-specific configuration (API base
                          URLs, default parameters, …). Secrets do NOT belong
                          here — they live with org-scoped integrations.

    Identifier/version/permissions note: the GRN is the canonical identifier
    (``name`` is the org-unique slug), ``Resource.version`` carries versioning,
    and ``required_capabilities`` is the PEEL permission binding — all
    inherited from the Universal Resource Model (ADR-009).
    """

    resource_type: ResourceType = ResourceType.TOOL

    name: str
    description: str
    category: ToolCategory
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    safety_level: SafetyLevel
    required_capabilities: list[str]
    runtime_binding: str
    execution_runtime: ExecutionRuntime = ExecutionRuntime.LOCAL
    enabled: bool = True
    configuration: dict[str, Any] = {}

    def public_view(self) -> dict[str, Any]:
        """Serializable representation safe to return from the API."""
        return {
            "grn": str(self.grn),
            "org_id": self.org_id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "safety_level": self.safety_level.value,
            "required_capabilities": self.required_capabilities,
            "runtime_binding": self.runtime_binding,
            "execution_runtime": self.execution_runtime.value,
            "enabled": self.enabled,
            "configuration": self.configuration,
            "state": self.state.value,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "metadata": self.metadata,
            "labels": self.labels,
        }

    @classmethod
    def create(
        cls,
        grn: GRN,
        org_id: str,
        created_by: str,
        name: str,
        description: str,
        category: ToolCategory,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
        safety_level: SafetyLevel,
        required_capabilities: list[str],
        runtime_binding: str,
        execution_runtime: ExecutionRuntime = ExecutionRuntime.LOCAL,
        enabled: bool = True,
        configuration: dict[str, Any] | None = None,
        labels: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "Tool":
        return cls(
            grn=grn,
            org_id=org_id,
            resource_type=ResourceType.TOOL,
            state=ResourceState.ACTIVE,
            version=1,
            created_by=created_by,
            updated_by=created_by,
            name=name,
            description=description,
            category=category,
            input_schema=input_schema,
            output_schema=output_schema,
            safety_level=safety_level,
            required_capabilities=required_capabilities,
            runtime_binding=runtime_binding,
            execution_runtime=execution_runtime,
            enabled=enabled,
            configuration=configuration or {},
            labels=labels or {},
            metadata=metadata or {},
        )