"""Identity bootstrap: Register Principal resource type into the registry.

This module ensures that Principal is registered as a resource type so it can be
created uniformly through the ResourceFactory, maintaining consistent identifier
and lifecycle management across the system (satisfies ADR-009).
"""

from __future__ import annotations

from gabriel.identity.principal import Principal
from gabriel.resource.registry import ResourceRegistry


def register_identity_resource_types(target_registry: ResourceRegistry | None = None) -> None:
    """Register identity resource types required by Gabriel bootstrap paths.

    The function is idempotent and safe to call multiple times.
    
    Registers:
    - Principal: The universal identity abstraction (keyed by PrincipalID)
      Future: User, Agent, SystemAgent, ServiceAccount extend Principal
    
    Args:
        target_registry: Registry to register into. If None, uses global registry.
    """
    from gabriel.resource.registry import registry

    reg = target_registry or registry

    if not reg.is_registered("principal"):
        reg.register(
            Principal,
            description="Universal identity abstraction for all actors",
            version="1.0",
            tags=frozenset({"identity", "core"}),
        )
