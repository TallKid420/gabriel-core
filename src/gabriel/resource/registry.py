"""Resource registry that maintains the Universal Resource Model.

Gabriel needs to know every resource type that exists:
- What it is (descriptor)
- How to validate it (validator)
- How to create it (factory)
- How to serialize it (serializer)
- What lifecycle it follows (lifecycle)
- What capabilities it exposes (descriptor)

This registry is the single source of truth for resource metadata.
"""
from typing import Type

from gabriel.resource.descriptor import ResourceDescriptor
from gabriel.resource.validators import ResourceValidator
from gabriel.resource.serializer import ResourceSerializer
from gabriel.resource.exceptions import (
    ResourceTypeNotRegisteredError,
    DuplicateResourceTypeError,
)


class ResourceRegistry:
    """Central registry for all resource types in Gabriel.
    
    Gabriel's Universal Resource Model: Everything that exists is a resource,
    and every resource type is registered here with complete metadata.
    
    No if/else chains — everything is data-driven.
    """
    
    def __init__(self) -> None:
        """Initialize empty registry."""
        self._descriptors: dict[str, ResourceDescriptor] = {}
        self._validators: dict[str, ResourceValidator] = {}
        self._serializers: dict[str, ResourceSerializer] = {}
    
    def register(
        self,
        descriptor_or_model: ResourceDescriptor | Type,
        lifecycle_class: Type | None = None,
        version: str = "1.0",
        description: str = "",
        capabilities: frozenset[str] | None = None,
        tags: frozenset[str] | None = None,
    ) -> ResourceDescriptor:
        """Register a resource descriptor or model class.

        This supports both forms:
        - ``registry.register(ResourceDescriptor(...))``
        - ``registry.register(Organization)``

        Args:
            descriptor_or_model: ResourceDescriptor or model class.
            lifecycle_class: Lifecycle class when registering a model class.
            version: Version string for model-class registration.
            description: Human-readable description.
            capabilities: Capabilities this resource exposes.
            tags: Optional tags for categorization.

        Returns:
            The registered ResourceDescriptor.

        Raises:
            DuplicateResourceTypeError: If type already registered.
        """
        if isinstance(descriptor_or_model, ResourceDescriptor):
            descriptor = descriptor_or_model
        else:
            model_class = descriptor_or_model
            if lifecycle_class is None:
                from gabriel.resource.lifecycle import LifecycleManager

                lifecycle_class = LifecycleManager

            descriptor = ResourceDescriptor(
                type_name=self._camel_to_snake(model_class.__name__),
                version=version,
                model=model_class,
                lifecycle_class=lifecycle_class,
                description=description,
                capabilities=capabilities or frozenset(),
                tags=tags or frozenset(),
            )

        if descriptor.type_name in self._descriptors:
            raise DuplicateResourceTypeError(
                f"Resource type '{descriptor.type_name}' is already registered"
            )

        self._descriptors[descriptor.type_name] = descriptor
        self._validators[descriptor.type_name] = ResourceValidator(descriptor)
        self._serializers[descriptor.type_name] = ResourceSerializer(descriptor)
        return descriptor
    
    def register_from_class(
        self,
        model_class: Type,
        lifecycle_class: Type,
        version: str = "1.0",
        description: str = "",
        capabilities: frozenset[str] | None = None,
        tags: frozenset[str] | None = None,
    ) -> ResourceDescriptor:
        """Register a resource type from a model class (convenience method).
        
        Args:
            model_class: The Pydantic model class.
            lifecycle_class: The lifecycle manager class.
            version: Version string (default "1.0").
            description: Human-readable description.
            capabilities: Set of capabilities this resource exposes.
            tags: Optional categorization tags.
            
        Returns:
            The created ResourceDescriptor.
            
        Raises:
            DuplicateResourceTypeError: If type already registered.
        """
        return self.register(
            model_class,
            lifecycle_class=lifecycle_class,
            version=version,
            description=description,
            capabilities=capabilities,
            tags=tags,
        )
    
    def get_descriptor(self, resource_type: str) -> ResourceDescriptor | None:
        """Get descriptor for a resource type.
        
        Args:
            resource_type: The type name.
            
        Returns:
            ResourceDescriptor if found, None otherwise.
        """
        return self._descriptors.get(resource_type)

    def get(self, resource_type: str) -> Type | None:
        """Get the registered model class for a resource type.

        Args:
            resource_type: The type name.

        Returns:
            The model class if registered, otherwise None.
        """
        descriptor = self.get_descriptor(resource_type)
        return descriptor.model if descriptor else None
    
    def get_validator(self, resource_type: str) -> ResourceValidator | None:
        """Get validator for a resource type.
        
        Args:
            resource_type: The type name.
            
        Returns:
            ResourceValidator if found, None otherwise.
        """
        return self._validators.get(resource_type)
    
    def get_serializer(self, resource_type: str) -> ResourceSerializer | None:
        """Get serializer for a resource type.
        
        Args:
            resource_type: The type name.
            
        Returns:
            ResourceSerializer if found, None otherwise.
        """
        return self._serializers.get(resource_type)
    
    def is_registered(self, resource_type: str) -> bool:
        """Check if a resource type is registered.
        
        Args:
            resource_type: The type name.
            
        Returns:
            True if registered, False otherwise.
        """
        return resource_type in self._descriptors
    
    def all_descriptors(self) -> list[ResourceDescriptor]:
        """Get all registered descriptors.
        
        Returns:
            List of all ResourceDescriptor instances.
        """
        return list(self._descriptors.values())
    
    def all_types(self) -> list[str]:
        """Get all registered type names.
        
        Returns:
            List of all resource type names.
        """
        return list(self._descriptors.keys())
    
    def unregister(self, resource_type: str) -> bool:
        """Unregister a resource type (mainly for testing).
        
        Args:
            resource_type: The type name.
            
        Returns:
            True if was registered and removed, False otherwise.
        """
        if resource_type in self._descriptors:
            del self._descriptors[resource_type]
            del self._validators[resource_type]
            del self._serializers[resource_type]
            return True
        return False
    
    @staticmethod
    def _camel_to_snake(name: str) -> str:
        """Convert CamelCase to snake_case.
        
        Args:
            name: CamelCase string.
            
        Returns:
            snake_case string.
        """
        result = []
        for i, char in enumerate(name):
            if char.isupper() and i > 0:
                result.append('_')
            result.append(char.lower())
        return ''.join(result)


# Global registry instance
registry = ResourceRegistry()