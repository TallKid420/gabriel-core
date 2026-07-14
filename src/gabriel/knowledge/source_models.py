"""KnowledgeSource resource: a named collection of documents for RAG.

A KnowledgeSource is a Universal Resource (GRN-addressed, versioned,
org-owned) that groups documents into a retrievable collection. Agents
reference knowledge sources by GRN (``AgentSpecification.knowledge_sources``)
and the gateway automatically retrieves relevant chunks from those sources
during chat turns.

V1 keeps membership simple: a document belongs to at most one knowledge
source (``Document.knowledge_source_grn`` column), avoiding a join table
until multi-source membership is actually needed.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from gabriel.resource.models import Resource, ResourceType


class KnowledgeSourceStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class KnowledgeSource(Resource):
    """A collection of documents used as retrieval grounding for agents."""

    resource_type: ResourceType = ResourceType.KNOWLEDGE_SOURCE

    name: str
    """Human-readable source name (e.g. "Product Handbook")."""

    description: str = ""
    """Optional description of what this source contains."""

    status: KnowledgeSourceStatus = KnowledgeSourceStatus.ACTIVE
    """Domain status: active (retrievable) or archived (excluded from RAG)."""

    document_count: int = 0
    """Denormalized count of attached documents (maintained by the service)."""

    def public_view(self) -> dict[str, Any]:
        """Serializable representation safe to return from the API."""
        return {
            "grn": str(self.grn),
            "org_id": self.org_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "document_count": self.document_count,
            "state": self.state.value,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "metadata": self.metadata,
            "labels": self.labels,
        }
