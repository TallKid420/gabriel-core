"""Resource serializers that convert between resource instances and data formats.

The serialization path:
    resource → dict → JSON → database → event

Serializers are pluggable per resource type via descriptor.
"""
from typing import Any
import json

from gabriel.resource.descriptor import ResourceDescriptor
from gabriel.resource.exceptions import ResourceSerializationError


class ResourceSerializer:
    """Serializes/deserializes resources through the unified Gabriel data path."""
    
    def __init__(self, descriptor: ResourceDescriptor) -> None:
        """Initialize serializer with descriptor metadata.
        
        Args:
            descriptor: ResourceDescriptor containing custom serializers.
        """
        self.descriptor = descriptor
    
    def serialize(self, resource: Any) -> dict[str, Any]:
        """Convert a resource instance to a dictionary.
        
        Path: resource → dict
        
        This dict can then be converted to JSON, stored in database, 
        or included in events.
        
        Args:
            resource: The resource instance to serialize.
            
        Returns:
            Dictionary representation of the resource.
            
        Raises:
            ResourceSerializationError: If serialization fails.
        """
        # If descriptor provides custom serializer, use it
        if self.descriptor.serializer_fn is not None:
            try:
                return self.descriptor.serializer_fn(resource)
            except Exception as e:
                raise ResourceSerializationError(
                    f"Custom serializer failed for {self.descriptor.type_name}: {e}"
                ) from e
        
        # Default: Use Pydantic's model_dump()
        try:
            data = resource.model_dump()
            
            # Ensure all values are JSON-serializable
            return self._ensure_json_serializable(data)
        except Exception as e:
            raise ResourceSerializationError(
                f"Failed to serialize {self.descriptor.type_name}: {e}"
            ) from e
    
    def deserialize(self, payload: dict[str, Any]) -> Any:
        """Convert a dictionary back to a resource instance.
        
        Path: dict → resource
        
        This is used when loading from database/events or REST API.
        
        Args:
            payload: Dictionary representation of a resource.
            
        Returns:
            Resource instance.
            
        Raises:
            ResourceSerializationError: If deserialization fails.
        """
        # If descriptor provides custom deserializer, use it
        if self.descriptor.deserializer_fn is not None:
            try:
                return self.descriptor.deserializer_fn(payload)
            except Exception as e:
                raise ResourceSerializationError(
                    f"Custom deserializer failed for {self.descriptor.type_name}: {e}"
                ) from e
        
        # Default: Use Pydantic's model_validate()
        try:
            return self.descriptor.model(**payload)
        except Exception as e:
            raise ResourceSerializationError(
                f"Failed to deserialize {self.descriptor.type_name}: {e}"
            ) from e
    
    def to_json(self, resource: Any) -> str:
        """Convert a resource to JSON string.
        
        Path: resource → dict → JSON
        
        Args:
            resource: The resource to convert.
            
        Returns:
            JSON string representation.
            
        Raises:
            ResourceSerializationError: If JSON encoding fails.
        """
        try:
            data = self.serialize(resource)
            return json.dumps(data, default=str)
        except ResourceSerializationError:
            raise
        except Exception as e:
            raise ResourceSerializationError(
                f"Failed to convert {self.descriptor.type_name} to JSON: {e}"
            ) from e
    
    def from_json(self, json_str: str) -> Any:
        """Convert a JSON string back to a resource instance.
        
        Path: JSON → dict → resource
        
        Args:
            json_str: JSON string representation.
            
        Returns:
            Resource instance.
            
        Raises:
            ResourceSerializationError: If JSON parsing or deserialization fails.
        """
        try:
            payload = json.loads(json_str)
            return self.deserialize(payload)
        except ResourceSerializationError:
            raise
        except Exception as e:
            raise ResourceSerializationError(
                f"Failed to parse JSON for {self.descriptor.type_name}: {e}"
            ) from e
    
    def _ensure_json_serializable(self, obj: Any) -> Any:
        """Recursively ensure all values are JSON-serializable.
        
        This handles edge cases like datetime, UUID, Enum, etc.
        """
        if isinstance(obj, dict):
            return {k: self._ensure_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._ensure_json_serializable(item) for item in obj]
        elif isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        else:
            # For other types (datetime, UUID, Enum, etc), convert to string
            return str(obj)
