"""Tool resource models."""

from typing import Any

from gabriel.resource.grn import GRN
from gabriel.resource.models import Resource, ResourceState, ResourceType


class Tool(Resource):
    """Declarative tool resource."""

    resource_type: ResourceType = ResourceType.TOOL

    name: str
    description: str
    category: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    safety_level: int
    required_capabilities: list[str]

    @classmethod
    def create(
        cls,
        grn: GRN,
        org_id: str,
        created_by: str,
        name: str,
        description: str,
        category: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
        safety_level: int,
        required_capabilities: list[str],
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
            labels=labels or {},
            metadata=metadata or {},
        )