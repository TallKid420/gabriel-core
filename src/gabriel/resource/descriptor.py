"""Resource descriptors that capture metadata about resource types."""
from dataclasses import dataclass
from typing import Any, Callable, Type


@dataclass(frozen=True)
class ResourceDescriptor:
    """Complete metadata about a resource type.
    
    This captures everything Gabriel needs to know about a resource type:
    - How to create it
    - How to validate it
    - How to serialize it
    - What lifecycle it follows
    - What capabilities it exposes
    
    No if/else chains needed — everything is data.
    """
    
    type_name: str
    """The resource type name (e.g., "organization", "policy", "principal")."""
    
    version: str
    """Version of this resource type (e.g., "1.0")."""
    
    model: Type
    """The Pydantic model class (e.g., Organization, Policy, Principal)."""
    
    lifecycle_class: Type
    """The lifecycle manager class for this resource type."""
    
    description: str
    """Human-readable description of this resource type."""
    
    capabilities: frozenset[str]
    """Capabilities exposed by this resource type."""
    
    validator_fn: Callable[[Any], bool] | None = None
    """Optional custom validation function. Signature: (instance) -> bool."""
    
    serializer_fn: Callable[[Any], dict[str, Any]] | None = None
    """Optional custom serializer. Signature: (instance) -> dict."""
    
    deserializer_fn: Callable[[dict[str, Any]], Any] | None = None
    """Optional custom deserializer. Signature: (dict) -> instance."""
    
    factory_fn: Callable[..., Any] | None = None
    """Optional custom factory function. Signature: (**kwargs) -> instance."""
    
    tags: frozenset[str] = frozenset()
    """Optional tags for categorization (e.g., "identity", "policy", "core")."""
    
    def __hash__(self) -> int:
        """Make descriptor hashable so it can be stored in sets/dicts."""
        return hash(self.type_name)
    
    def __eq__(self, other: object) -> bool:
        """Descriptors are equal if they describe the same type."""
        if not isinstance(other, ResourceDescriptor):
            return False
        return self.type_name == other.type_name
