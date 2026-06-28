from gabriel.resource.models import Resource, ResourceType

class Organization(Resource):
    resource_type: ResourceType = ResourceType.ORGANIZATION
    display_name: str
    description: str | None = None
    # TODO Settings/Policies can be added here later