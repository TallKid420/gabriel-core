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
            capabilities=frozenset(
                {
                    "document:create",
                    "document:read",
                    "document:update",
                    "document:delete",
                }
            ),
        )

    # Register Agent resource type (ingestion target).
    if not reg.is_registered("agent"):
        from gabriel.agent.models import Agent

        reg.register(
            Agent,
            description="Agent resource",
            version="1.0",
            tags=frozenset({"core", "agent"}),
            capabilities=frozenset(
                {
                    "agent:create",
                    "agent:read",
                    "agent:update",
                    "agent:delete",
                    "agent:execute",
                    "agent:enable",
                    "agent:disable",
                }
            ),
        )

    # Register the Policy resource type (ingestion target).
    if not reg.is_registered("policy"):
        from gabriel.policy.models import Policy

        reg.register(
            Policy,
            description="Policy resource",
            version="1.0",
            tags=frozenset({"core", "policy"}),
            capabilities=frozenset(
                {
                    "policy:create",
                    "policy:read",
                    "policy:update",
                    "policy:delete",
                }
            ),
        )

    # Register the Tool resource type.
    if not reg.is_registered("tool"):
        from gabriel.tool.models import Tool

        reg.register(
            Tool,
            description="Tool resource",
            version="1.0",
            tags=frozenset({"core", "tool"}),
            capabilities=frozenset(
                {
                    "tool:create",
                    "tool:read",
                    "tool:update",
                    "tool:delete",
                }
            ),
        )

    # Register the Conversation resource type (Phase 2 — Core Business Logic).
    if not reg.is_registered("conversation"):
        from gabriel.conversation.models import Conversation

        reg.register(
            Conversation,
            description="Conversation resource",
            version="1.0",
            tags=frozenset({"core", "conversation"}),
            capabilities=frozenset(
                {
                    "conversation:create",
                    "conversation:read",
                    "conversation:update",
                    "conversation:delete",
                }
            ),
        )

    # Register the Message resource type (Phase 2 — Core Business Logic).
    if not reg.is_registered("message"):
        from gabriel.conversation.message_models import Message

        reg.register(
            Message,
            description="Conversation message resource",
            version="1.0",
            tags=frozenset({"core", "conversation"}),
            capabilities=frozenset(
                {
                    "message:create",
                    "message:read",
                }
            ),
        )

    # Register the Notification resource type (Phase 2 — Core Business Logic).
    if not reg.is_registered("notification"):
        from gabriel.notification.models import Notification

        reg.register(
            Notification,
            description="Notification resource",
            version="1.0",
            tags=frozenset({"core", "notification"}),
            capabilities=frozenset(
                {
                    "notification:create",
                    "notification:read",
                    "notification:update",
                }
            ),
        )

    # Register the MemoryLayerEntry resource type (Phase 2 — Core Business Logic).
    if not reg.is_registered("memory_layer_entry"):
        from gabriel.memory.layer_models import MemoryLayerEntry

        reg.register(
            MemoryLayerEntry,
            description="Governed memory layer entry",
            version="1.0",
            tags=frozenset({"core", "memory"}),
            capabilities=frozenset(
                {
                    "memory:create",
                    "memory:read",
                    "memory:update",
                    "memory:delete",
                }
            ),
        )

    # Register the KnowledgeSource resource type (Phase 4 — Document & Knowledge).
    if not reg.is_registered("knowledge_source"):
        from gabriel.knowledge.source_models import KnowledgeSource

        reg.register(
            KnowledgeSource,
            description="Knowledge source (document collection for RAG)",
            version="1.0",
            tags=frozenset({"core", "knowledge"}),
            capabilities=frozenset(
                {
                    "knowledge:create",
                    "knowledge:read",
                    "knowledge:update",
                    "knowledge:delete",
                    "knowledge:search",
                }
            ),
        )

    # Register identity types (Principal, future: User, Agent, etc.)
    from gabriel.identity.bootstrap import register_identity_resource_types
    register_identity_resource_types(reg)
