"""Organization domain handlers and events."""
from gabriel.events.command import Command
from gabriel.events.event import Event
from gabriel.events.handler import Handler
from gabriel.events.exceptions import CommandValidationError, HandlerExecutionError
from gabriel.resource.models import ResourceState
from gabriel.resource.grn import GRN
from gabriel.resource.factory import ResourceFactory
from gabriel.resource.registry import registry
from gabriel.resource.bootstrap import register_core_resource_types


class CreateOrganizationHandler(Handler):
    """Handler for CreateOrganizationCommand.
    
    Creates an Organization and emits OrganizationCreated event.
    """

    def __init__(self, factory: ResourceFactory | None = None):
        register_core_resource_types()
        self.factory = factory or ResourceFactory(registry)

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
            grn = GRN.generate(
                org_id=org_slug,
                resource_type="organization",
            )

            org = self.factory.create(
                "organization",
                grn=grn,
                org_id=org_slug,
                display_name=display_name,
                description=description,
                state=ResourceState.ACTIVE,
                created_by=command.principal_id,
                updated_by=command.principal_id,
            )

            # 3. Emit OrganizationCreated event
            event = Event(
                type="organization_created",
                principal_id=command.principal_id,
                organization_id=command.organization_id,
                resource_grn=str(grn),
                correlation_id=command.correlation_id,
                payload={
                    "display_name": org.display_name,
                    "description": org.description,
                    "grn": str(org.grn),
                    "org_id": org.org_id,
                },
            )

            return [event]

        except CommandValidationError:
            raise
        except Exception as exc:
            raise HandlerExecutionError(f"Failed to create organization: {exc}") from exc
