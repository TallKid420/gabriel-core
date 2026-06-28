"""Execution context: The immutable "process" of Gabriel."""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
import json

from gabriel.resource.grn import GRN
from gabriel.identity.principal import Principal


@dataclass(frozen=True)
class ExecutionContext:
    """Immutable execution context.
    
    An ExecutionContext is like a Process Control Block (PCB) in an OS.
    Every operation executes within a context that determines:
    - Who is executing (principal)
    - What organization they belong to
    - What resource they're operating on
    - What capabilities they have
    - Tracing info (correlation/causation IDs)
    """

    execution_id: UUID
    """Unique identifier for this execution."""

    principal: Principal
    """The Principal (user, agent, etc.) executing."""

    organization: str
    """The organization this execution belongs to (tenant isolation)."""

    correlation_id: UUID
    """Trace ID for correlating related events and executions."""

    causation_id: UUID | None
    """The execution/event that caused this execution (causal ordering)."""

    session_id: UUID | None
    """Optional session ID for grouping related executions."""

    resource: GRN | None
    """Optional resource this execution concerns."""

    started_at: datetime
    """When this execution started."""

    capabilities: frozenset[str]
    """Capabilities the principal has (immutable)."""

    metadata: dict[str, str]
    """Extensible metadata."""

    def __hash__(self) -> int:
        """Make context hashable (for use in sets/dicts)."""
        return hash((
            self.execution_id,
            self.principal.id.org_id,  # Use org_id from principal
            self.organization,
            self.correlation_id,
            self.causation_id,
            self.session_id,
            str(self.resource) if self.resource else None,
            self.started_at,
        ))

    def __eq__(self, other: object) -> bool:
        """Compare contexts for equality."""
        if not isinstance(other, ExecutionContext):
            return False
        return (
            self.execution_id == other.execution_id
            and self.organization == other.organization
            and self.principal == other.principal
            and self.correlation_id == other.correlation_id
        )

    def __str__(self) -> str:
        return f"ExecutionContext(id={self.execution_id}, org={self.organization}, principal={self.principal.id})"

    def __repr__(self) -> str:
        return f"ExecutionContext(execution_id={self.execution_id!r}, principal={self.principal!r})"

    def to_dict(self) -> dict:
        """Serialize context to dict for storage/transmission.
        
        Returns:
            dict: Serializable representation.
        """
        return {
            "execution_id": str(self.execution_id),
            "principal_id": str(self.principal.id),
            "organization": self.organization,
            "correlation_id": str(self.correlation_id),
            "causation_id": str(self.causation_id) if self.causation_id else None,
            "session_id": str(self.session_id) if self.session_id else None,
            "resource": str(self.resource) if self.resource else None,
            "started_at": self.started_at.isoformat(),
            "capabilities": sorted(list(self.capabilities)),
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Serialize context to JSON string.
        
        Returns:
            str: JSON representation.
        """
        return json.dumps(self.to_dict(), indent=2)

    def has_capability(self, capability: str) -> bool:
        """Check if principal has a capability.
        
        Args:
            capability: The capability to check.
            
        Returns:
            bool: True if principal has capability.
        """
        return capability in self.capabilities