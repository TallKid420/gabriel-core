"""Principal: The universal identity object in Gabriel."""
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from gabriel.identity.principal_id import PrincipalID
from gabriel.identity.models import PrincipalType, PrincipalStatus, Capability


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Principal(BaseModel):
    """Universal identity abstraction.
    
    A Principal is anyone or anything that can act on Gabriel resources.
    
    Later:
    - User extends Principal
    - Agent extends Principal
    - SystemAgent extends Principal
    - ServiceAccount extends Principal
    
    This is the root identity object.
    """

    id: PrincipalID
    """Globally unique identifier for this principal."""

    resource_grn: str | None = None
    """Optional GRN mirror link to the corresponding User/Agent resource."""

    organization_id: str
    """The organization this principal belongs to (tenant isolation)."""

    principal_type: PrincipalType
    """What kind of principal this is."""

    display_name: str
    """Human-readable name."""

    status: PrincipalStatus = PrincipalStatus.ACTIVE
    """Current lifecycle state."""

    capabilities: set[Capability] = Field(default_factory=set)
    """Capabilities this principal has (not permissions; those come via PEEL)."""

    metadata: dict[str, Any] = Field(default_factory=dict)
    """Extensible metadata."""

    created_at: datetime = Field(default_factory=utcnow)
    """When this principal was created."""

    updated_at: datetime = Field(default_factory=utcnow)
    """When this principal was last updated."""

    # Immutable
    model_config = {"frozen": True}

    def can(self, capability: Capability) -> bool:
        """Check if this principal has a capability.
        
        Note: This checks *capability*, not permission.
        Permissions (whether capability can be exercised) come from PEEL.
        """
        return capability in self.capabilities

    def is_active(self) -> bool:
        """Check if this principal is in active status."""
        return self.status == PrincipalStatus.ACTIVE
