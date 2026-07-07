"""Organization projection: builds organizations read model from events."""

from gabriel.events.event import Event
from gabriel.events.projection import Projection


class OrganizationProjection(Projection):
    """Projection that maintains the organizations read model."""

    def __init__(self):
        self.organizations: dict[str, dict] = {}

    @property
    def event_types(self) -> list[str]:
        return ["organization_created"]

    async def handle_event(self, event: Event) -> None:
        if event.type == "organization_created":
            await self._handle_organization_created(event)

    async def _handle_organization_created(self, event: Event) -> None:
        grn = event.resource_grn
        if not grn:
            return

        self.organizations[grn] = {
            "grn": grn,
            "org_id": event.payload.get("org_id"),
            "display_name": event.payload.get("display_name"),
            "description": event.payload.get("description"),
            "created_by": event.principal_id,
            "created_at": event.occurred_at,
        }

    async def reset(self) -> None:
        self.organizations.clear()

    def get_organization(self, grn: str) -> dict | None:
        return self.organizations.get(grn)

    def list_organizations(self) -> list[dict]:
        return list(self.organizations.values())
