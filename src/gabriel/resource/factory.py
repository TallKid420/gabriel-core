"""Resource factory that creates instances through the registry.

Instead of:
    Organization(...)
    Policy(...)
    Principal(...)

Future code becomes:
    factory.create("organization", ...)
    factory.create("policy", ...)
    factory.create("principal", ...)

No if/else chains — everything is data-driven from the registry.
"""
from typing import Any

from gabriel.resource.descriptor import ResourceDescriptor
from gabriel.resource.exceptions import ResourceFactoryError, ResourceTypeNotRegisteredError


class ResourceFactory:
    """Factory for creating resource instances through the registry."""
    
    def __init__(self, registry: "ResourceRegistry") -> None:
        """Initialize factory with a registry.
        
        Args:
            registry: ResourceRegistry containing all registered descriptors.
        """
        self.registry = registry
    
    def create(
        self,
        resource_type: str,
        **kwargs: Any,
    ) -> Any:
        """Create a resource instance.
        
        Args:
            resource_type: The type name (e.g., "organization", "policy").
            **kwargs: Arguments passed to the resource constructor or factory_fn.
            
        Returns:
            The created resource instance.
            
        Raises:
            ResourceTypeNotRegisteredError: If type not registered.
            ResourceFactoryError: If creation fails.
        """
        # Look up descriptor
        descriptor = self.registry.get_descriptor(resource_type)
        
        if descriptor is None:
            raise ResourceTypeNotRegisteredError(
                f"Resource type '{resource_type}' is not registered"
            )
        
        try:
            # If descriptor has custom factory, use it
            if descriptor.factory_fn is not None:
                return descriptor.factory_fn(**kwargs)
            
            # If model has a create() class method, use it
            if hasattr(descriptor.model, "create") and callable(getattr(descriptor.model, "create")):
                return descriptor.model.create(**kwargs)
            
            # Otherwise, instantiate directly
            return descriptor.model(**kwargs)
        except Exception as e:
            raise ResourceFactoryError(
                f"Failed to create {resource_type}: {e}"
            ) from e
    
    def create_from_dict(
        self,
        resource_type: str,
        data: dict[str, Any],
    ) -> Any:
        """Create a resource from a dictionary (e.g., from JSON/API).
        
        This uses the deserializer, so it's the deserialization path:
            dict → resource
        
        Args:
            resource_type: The type name.
            data: Dictionary representation of the resource.
            
        Returns:
            The created resource instance.
            
        Raises:
            ResourceTypeNotRegisteredError: If type not registered.
            ResourceFactoryError: If creation fails.
        """
        descriptor = self.registry.get_descriptor(resource_type)
        
        if descriptor is None:
            raise ResourceTypeNotRegisteredError(
                f"Resource type '{resource_type}' is not registered"
            )
        
        try:
            # If descriptor has custom deserializer, use it
            if descriptor.deserializer_fn is not None:
                return descriptor.deserializer_fn(data)
            
            # Otherwise, use model instantiation
            return descriptor.model(**data)
        except Exception as e:
            raise ResourceFactoryError(
                f"Failed to create {resource_type} from dict: {e}"
            ) from e


# Forward reference for type hints
from gabriel.resource.registry import ResourceRegistry  # noqa: E402, F401
