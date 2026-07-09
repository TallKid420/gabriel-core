"""ExternalIntegration resource model.

An ExternalIntegration stores the org-scoped credentials (OAuth tokens,
IMAP/SMTP configs, API keys) required by integration tool libraries
(email, calendar, etc.).

Design principles
-----------------
- One record per integration per org (e.g. one Gmail config per org).
- Credentials are stored as a free-form dict.  In production, the database
  column MUST be encrypted at rest (column-level encryption or a KMS envelope).
- The resource follows the standard Gabriel vertical-slice pattern (ADR-009):
  model → ORM → mapper → repo → service.
- PEEL gates ``integration:read`` / ``integration:update`` via
  ``READ_RESOURCE`` / ``WRITE_RESOURCE`` capabilities.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from gabriel.resource.grn import GRN
from gabriel.resource.models import Resource, ResourceState, ResourceType


class IntegrationType(str, Enum):
    """Supported third-party integration backends."""

    GMAIL = "gmail"
    GOOGLE_CALENDAR = "google_calendar"
    IMAP_SMTP = "imap_smtp"
    CUSTOM = "custom"


class ExternalIntegration(Resource):
    """Org-scoped external integration configuration.

    Fields
    ------
    integration_type : Which backend this record represents.
    display_name     : Human-readable name (e.g. "Work Gmail").
    credentials      : JSON blob of access tokens / passwords.
                       MUST be encrypted at rest in production.
    scopes           : Comma-separated list of OAuth scopes granted.
    is_active        : Whether the credentials are currently valid.
    """

    resource_type: ResourceType = ResourceType.TOOL  # re-uses TOOL slot — see note

    integration_type: IntegrationType
    display_name: str
    credentials: dict[str, Any]
    scopes: str
    is_active: bool

    @classmethod
    def create(
        cls,
        grn: GRN,
        org_id: str,
        created_by: str,
        integration_type: IntegrationType,
        display_name: str,
        credentials: dict[str, Any],
        scopes: str = "",
        is_active: bool = True,
        labels: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ExternalIntegration":
        return cls(
            grn=grn,
            org_id=org_id,
            resource_type=ResourceType.TOOL,
            state=ResourceState.ACTIVE,
            version=1,
            created_by=created_by,
            updated_by=created_by,
            integration_type=integration_type,
            display_name=display_name,
            credentials=credentials,
            scopes=scopes,
            is_active=is_active,
            labels=labels or {},
            metadata=metadata or {},
        )
