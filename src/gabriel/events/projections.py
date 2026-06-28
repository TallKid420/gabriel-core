"""Organization projection: Builds organizations read model from events."""
from gabriel.events.event import Event
from gabriel.events.projection import Projection


class OrganizationProjection(Projection):
    """Projection that maintains the organizations read model.
    
    Subscribes to organization events and maintains an in-memory
    organizations table. In production, this would update a Postgres
    table instead.
    """

    def __init__(self):
        """Initialize the projection with empty state."""
        self.organizations: dict[str, dict] = {}  # grn → organization data

    @property
    def event_types(self) -> list[str]:
        return ["organization_created"]

    async def handle_event(self, event: Event) -> None:
        """Handle an event and update the organizations table.
        
        Args:
            event: The event to handle.
        """
        if event.type == "organization_created":
            await self._handle_organization_created(event)

    async def _handle_organization_created(self, event: Event) -> None:
        """Handle OrganizationCreated event.
        
        Args:
            event: The event.
        """
        grn = event.resource_grn
        if not grn:
            return

        # Build organization read model
        organization = {
            "grn": grn,
            "org_id": event.payload.get("org_id"),
            "display_name": event.payload.get("display_name"),
            "description": event.payload.get("description"),
            "created_by": event.principal_id,
            "created_at": event.occurred_at,
        }

        self.organizations[grn] = organization

    async def reset(self) -> None:
        """Reset projection to initial state."""
        self.organizations.clear()

    def get_organization(self, grn: str) -> dict | None:
        """Get an organization from the read model.
        
        Args:
            grn: The organization GRN.
            
        Returns:
            dict | None: The organization or None if not found.
        """
        return self.organizations.get(grn)

    def list_organizations(self) -> list[dict]:
        """List all organizations in the read model.
        
        Returns:
            list[dict]: All organizations.
        """
        return list(self.organizations.values())
