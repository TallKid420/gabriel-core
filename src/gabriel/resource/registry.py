from dataclasses import dataclass, field
from gabriel.resource.models import ResourceType
from gabriel.resource.exceptions import (
    ResourceTypeNotRegisteredError,
    DuplicateResourceTypeError,
)

@dataclass
class ResourceTypeDefinition:
    resource_type: ResourceType
    description: str
    schema_version: str = "1.0"
    tags: list[str] = field(default_factory=list)

class TypeRegistry:
    def __init__(self) -> None:
        self._registry: dict[ResourceType, ResourceTypeDefinition] = {}

    def register(self, definition: ResourceTypeDefinition) -> None:
        """Raises DuplicateResourceTypeError if already registered"""
        if definition.resource_type in self._registry:
            raise DuplicateResourceTypeError(f"Resource type {definition.resource_type} is already registered")
        self._registry[definition.resource_type] = definition

    def get(self, resource_type: ResourceType) -> ResourceTypeDefinition:
        """Raises ResourceTypeNotRegisteredError if not found"""
        if resource_type not in self._registry:
            raise ResourceTypeNotRegisteredError(f"Resource type {resource_type} is not registered")
        return self._registry[resource_type]

    def all(self) -> list[ResourceTypeDefinition]:
        """Returns all registered definitions"""
        return list(self._registry.values())

    def is_registered(self, resource_type: ResourceType) -> bool:
        """Returns True if the resource type is registered, False otherwise"""
        return resource_type in self._registry

# Global registry instance
registry = TypeRegistry()