"""Organization domain handlers and events."""
from gabriel.events.command import Command
from gabriel.events.event import Event
from gabriel.events.handler import Handler
from gabriel.events.exceptions import CommandValidationError, HandlerExecutionError
from gabriel.resource.models import ResourceType
from gabriel.resource.grn import GRN


class CreateOrganizationHandler(Handler):
    """Handler for CreateOrganizationCommand.
    
    Creates an Organization and emits OrganizationCreated event.
    """

    @property
    def command_type(self) -> str:
        return "create_organization"

    async def handle(self, command: Command) -> list[Event]:
        """Handle CreateOrganizationCommand.
        
        Payload expected:
        {
            "display_name": "Acme Corp",
            "description": "A company"
        }
        """
        try:
            # 1. Extract and validate payload
            display_name = command.payload.get("display_name")
            description = command.payload.get("description")

            if not display_name:
                raise CommandValidationError("display_name is required")

            if not isinstance(display_name, str) or not display_name.strip():
                raise CommandValidationError("display_name must be a non-empty string")

            # 2. Generate organization GRN
            org_slug = display_name.lower().replace(" ", "-")
            grn = GRN(
                org_id=org_slug,
                resource_type=ResourceType.ORGANIZATION,
                resource_id=org_slug,
            )

            # 3. Emit OrganizationCreated event
            event = Event(
                type="organization_created",
                principal_id=command.principal_id,
                organization_id=command.organization_id,
                resource_grn=str(grn),
                correlation_id=command.correlation_id,
                payload={
                    "display_name": display_name,
                    "description": description,
                    "grn": str(grn),
                    "org_id": org_slug,
                },
            )

            return [event]

        except CommandValidationError:
            raise
        except Exception as exc:
            raise HandlerExecutionError(f"Failed to create organization: {exc}") from exc
