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
            labels=labels or {},
            metadata=metadata or {},
        )