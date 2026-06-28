"""Agent resource models."""

from typing import Any

from gabriel.agent.specification import AgentSpecification
from gabriel.resource.grn import GRN
from gabriel.resource.models import Resource, ResourceState, ResourceType


class Agent(Resource):
    """Declarative agent resource. Agents are resources."""

    resource_type: ResourceType = ResourceType.AGENT
    specification: AgentSpecification
    enabled: bool = True

    @classmethod
    def create(
        cls,
        grn: GRN,
        org_id: str,
        created_by: str,
        specification: AgentSpecification,
        enabled: bool = True,
        labels: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "Agent":
        return cls(
            grn=grn,
            org_id=org_id,
            resource_type=ResourceType.AGENT,
            state=ResourceState.ACTIVE,
            version=1,
            created_by=created_by,
            updated_by=created_by,
            specification=specification,
            enabled=enabled,
            labels=labels or {},
            metadata=metadata or {},
        )