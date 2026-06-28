"""Scoped client: Access to resources within an execution context."""
from gabriel.runtime.context import ExecutionContext
from gabriel.runtime.capabilities import Capability
from gabriel.runtime.exceptions import CapabilityError


class ScopedClient:
    """Client for accessing resources within an execution context.
    
    Instead of:
        db.query(...)
        tools.invoke(...)
    
    Use:
        context.principal
        context.has_capability(...)
    
    The context determines what is available.
    """

    def __init__(self, context: ExecutionContext):
        """Initialize scoped client.
        
        Args:
            context: The execution context to scope to.
        """
        self.context = context

    @property
    def principal(self):
        """Get the principal executing.
        
        Returns:
            Principal: The principal from context.
        """
        return self.context.principal

    @property
    def organization_id(self) -> str:
        """Get the organization ID.
        
        Returns:
            str: The organization from context.
        """
        return self.context.organization

    @property
    def execution_id(self):
        """Get the execution ID.
        
        Returns:
            UUID: The execution ID from context.
        """
        return self.context.execution_id

    @property
    def correlation_id(self):
        """Get the correlation ID for tracing.
        
        Returns:
            UUID: The correlation ID from context.
        """
        return self.context.correlation_id

    def has_capability(self, capability: Capability | str) -> bool:
        """Check if principal has a capability.
        
        Args:
            capability: The capability to check (Capability enum or string).
            
        Returns:
            bool: True if principal has the capability.
        """
        cap_str = capability.value if isinstance(capability, Capability) else capability
        return self.context.has_capability(cap_str)

    def require_capability(self, capability: Capability | str) -> None:
        """Require a capability, raising CapabilityError if missing.
        
        Args:
            capability: The capability to require.
            
        Raises:
            CapabilityError: If principal lacks the capability.
        """
        if not self.has_capability(capability):
            cap_str = capability.value if isinstance(capability, Capability) else capability
            raise CapabilityError(
                f"Principal {self.principal.id} lacks capability: {cap_str}"
            )

    def metadata(self, key: str) -> str | None:
        """Get metadata value from context.
        
        Args:
            key: The metadata key.
            
        Returns:
            str | None: The metadata value or None if not found.
        """
        return self.context.metadata.get(key)

    def __repr__(self) -> str:
        return f"ScopedClient(principal={self.principal.id}, org={self.organization_id})"
