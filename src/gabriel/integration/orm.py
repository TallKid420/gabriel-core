"""SQLAlchemy ORM model for ExternalIntegration."""

from typing import Any

from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from gabriel.database import Base, GabrielResourceMixin


class ExternalIntegrationORM(Base, GabrielResourceMixin):
    """Persistence layer for :class:`~gabriel.integration.models.ExternalIntegration`.

    The ``credentials`` column stores OAuth tokens / IMAP-SMTP passwords as JSON.
    Production deployments MUST apply column-level encryption or a KMS envelope
    to this column before any real credentials are written.
    """

    __tablename__ = "external_integrations"

    # e.g. "gmail", "google_calendar", "imap_smtp"
    integration_type: Mapped[str] = mapped_column(String(64), nullable=False)

    display_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    # Raw credentials JSON — encrypt at rest in production
    credentials: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    # Comma-separated OAuth scopes
    scopes: Mapped[str] = mapped_column(String(1024), nullable=False, default="")

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
