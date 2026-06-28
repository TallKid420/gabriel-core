from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Enum, Integer, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gabriel.resource.models import ResourceState, ResourceType


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class GabrielResourceMixin:
    """Shared columns used by all persisted Gabriel resources."""

    grn: Mapped[str] = mapped_column(String(255), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    resource_type: Mapped[ResourceType] = mapped_column(
        Enum(ResourceType, native_enum=False), nullable=False
    )
    state: Mapped[ResourceState] = mapped_column(
        Enum(ResourceState, native_enum=False), nullable=False, default=ResourceState.DRAFT
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    # Use an attribute name that does not conflict with SQLAlchemy's metadata on Base.
    resource_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    labels: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)