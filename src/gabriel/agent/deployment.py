"""Deployment service for creating Agent resources from specifications."""

from collections import defaultdict
from uuid import uuid4

from gabriel.agent.exceptions import AgentDeploymentError
from gabriel.agent.models import Agent
from gabriel.agent.specification import AgentSpecification
from gabriel.agent.validator import AgentValidator
from gabriel.events.event import Event
from gabriel.events.event_store import EventStore
from gabriel.resource.grn import GRN
from gabriel.resource.registry import ResourceRegistry


class AgentDeploymentService:
    """Deploys Agent resources. No runtime execution occurs here."""

    def __init__(
        self,
        validator: AgentValidator,
        event_store: EventStore,
        registry: ResourceRegistry,
    ) -> None:
        self.validator = validator
        self.event_store = event_store
        self.registry = registry
        self._trigger_registry: dict[str, list[str]] = defaultdict(list)

    async def deploy(
        self,
        specification: AgentSpecification,
        org_id: str = "org-default",
        created_by: str = "principal://org-default/system/deployer",
    ) -> Agent:
        """Validate and deploy an agent resource.

        Steps:
        1) validate specification
        2) create Agent resource
        3) emit AgentCreated event
        4) register triggers
        """
        self.validator.validate(specification)

        descriptor = self.registry.get_descriptor("agent")
        if descriptor is None:
            raise AgentDeploymentError("Resource type 'agent' is not registered")

        agent = Agent.create(
            grn=GRN.generate(org_id=org_id, resource_type="agent"),
            org_id=org_id,
            created_by=created_by,
            specification=specification,
            metadata=specification.metadata,
        )

        self.event_store.append(
            Event(
                type="AgentCreated",
                principal_id=created_by,
                organization_id=org_id,
                resource_grn=str(agent.grn),
                payload={"name": specification.name, "runtime": specification.runtime},
            )
        )

        for trigger in specification.normalized_triggers():
            self._trigger_registry[trigger.event_type].append(str(agent.grn))

        return agent

    def triggers_for_event(self, event_type: str) -> list[str]:
        """Return deployed agent GRNs registered for an event type."""
        return list(self._trigger_registry.get(event_type, []))