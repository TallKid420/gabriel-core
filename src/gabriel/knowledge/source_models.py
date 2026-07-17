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


class KnowledgeSourceType(str, Enum):
    """What kind of knowledge backs this source.

    Agents reference knowledge sources by GRN only — the type is an
    implementation detail resolved by the knowledge module, never by the
    agent or the chat runtime (no coupling to any vector DB).

    VECTOR_COLLECTION   — chunked + embedded documents, similarity-searched
                          at chat time (the V1 RAG default).
    DOCUMENT_COLLECTION — a plain grouping of uploaded documents that agents
                          can reference as a document library (retrieval uses
                          the keyword/chunk fallback; no embedding required).
    EXTERNAL            — future: an external knowledge base reached through
                          a connector (Confluence, Notion, SharePoint, …).
                          Connection details live in ``metadata``/connector
                          resources, not on this model.
    """

    VECTOR_COLLECTION = "vector_collection"
    DOCUMENT_COLLECTION = "document_collection"
    EXTERNAL = "external"


class KnowledgeSource(Resource):
    """A collection of documents used as retrieval grounding for agents."""

    resource_type: ResourceType = ResourceType.KNOWLEDGE_SOURCE

    name: str
    """Human-readable source name (e.g. "Product Handbook")."""

    description: str = ""
    """Optional description of what this source contains."""

    status: KnowledgeSourceStatus = KnowledgeSourceStatus.ACTIVE
    """Domain status: active (retrievable) or archived (excluded from RAG)."""

    source_type: KnowledgeSourceType = KnowledgeSourceType.VECTOR_COLLECTION
    """Kind of knowledge backing this source (see :class:`KnowledgeSourceType`)."""

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
            "source_type": self.source_type.value,
            "document_count": self.document_count,
            "state": self.state.value,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "metadata": self.metadata,
            "labels": self.labels,
        }
