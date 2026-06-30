"""Resource bootstrap helpers.

Registers core resource types into the global registry so factories can create
domain models without ad-hoc per-call registration.

This implements ADR-009 (GRN Factory Integration): All resource creation is
routed through ResourceFactory, ensuring uniform identifier minting and default
handling across the system.
"""

from __future__ import annotations

from gabriel.organization.models import Organization
from gabriel.resource.registry import ResourceRegistry, registry


def register_core_resource_types(target_registry: ResourceRegistry | None = None) -> None:
    """Register core resource types required by Gabriel bootstrap paths.

    The function is idempotent and safe to call multiple times.
    
    Registers:
    - Organization: Tenancy root resource
    - Principal: Universal identity (via identity.bootstrap)
    """
    reg = target_registry or registry

    # Register Organization resource type
    if not reg.is_registered("organization"):
        reg.register(
            Organization,
            description="Tenancy root",
            version="1.0",
            tags=frozenset({"core", "tenancy"}),
        )

    # Register identity types (Principal, future: User, Agent, etc.)
    from gabriel.identity.bootstrap import register_identity_resource_types
    register_identity_resource_types(reg)
