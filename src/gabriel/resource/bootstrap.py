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

    # Register the Document resource type (ingestion target).
    if not reg.is_registered("document"):
        from gabriel.document.models import Document

        reg.register(
            Document,
            description="Ingested document resource",
            version="1.0",
            tags=frozenset({"core", "content"}),
        )

    # Register Agent resource type (ingestion target).
    if not reg.is_registered("agent"):
        from gabriel.agent.models import Agent

        reg.register(
            Agent,
            description="Agent resource",
            version="1.0",
            tags=frozenset({"core", "agent"}),
            # capabilities=[Capability.AGENT_CREATE, Capability.AGENT_UPDATE, Capability.AGENT_DELETE], # FIXME: Next_Development_Milestones.pdf - Task 1.1
        )

    # Register the Policy resource type (ingestion target).
    if not reg.is_registered("policy"):
        from gabriel.policy.models import Policy

        reg.register(
            Policy,
            description="Policy resource",
            version="1.0",
            tags=frozenset({"core", "policy"}),
        )

    # # Register the Notification resource type (ingestion target).
    # if not reg.is_registered("notification"):
    #     from gabriel.notification.models import Notification

    #     reg.register(
    #         Notification,
    #         description="Notification resource",
    #         version="1.0",
    #         tags=frozenset({"core", "notification"}),
    #     )

    # Register identity types (Principal, future: User, Agent, etc.)
    from gabriel.identity.bootstrap import register_identity_resource_types
    register_identity_resource_types(reg)
