"""Schema helpers for registry-managed resource models."""

from typing import Any

from gabriel.resource.registry import ResourceRegistry
from gabriel.resource.exceptions import ResourceTypeNotRegisteredError


class ResourceSchema:
    """Build JSON-schema metadata from registered resource descriptors."""

    def __init__(self, registry: ResourceRegistry) -> None:
        self.registry = registry

    def for_type(self, resource_type: str) -> dict[str, Any]:
        """Return the model JSON schema for a registered resource type."""
        descriptor = self.registry.get_descriptor(resource_type)
        if descriptor is None:
            raise ResourceTypeNotRegisteredError(
                f"Resource type '{resource_type}' is not registered"
            )

        schema = descriptor.model.model_json_schema()
        schema["title"] = descriptor.type_name
        schema["x-gabriel-version"] = descriptor.version
        schema["x-gabriel-capabilities"] = sorted(list(descriptor.capabilities))
        return schema
