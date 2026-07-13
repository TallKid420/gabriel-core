"""Persistence model for the Notification resource."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from gabriel.database.base import Base, GabrielResourceMixin


class NotificationORM(Base, GabrielResourceMixin):
    """Notification table — per-recipient alerts derived from events."""

    __tablename__ = "notifications"
    __table_args__ = (
        # Listing pattern: a recipient's notifications, unread first / newest first.
        Index("ix_notifications_recipient_read", "recipient", "read"),
        Index("ix_notifications_org_recipient_created", "org_id", "recipient", "created_at"),
    )

    recipient: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
