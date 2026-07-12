"""Persistence model for the Conversation resource."""
from __future__ import annotations

from sqlalchemy import Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from gabriel.database.base import Base, GabrielResourceMixin


class ConversationORM(Base, GabrielResourceMixin):
    """Conversation table — org-scoped conversation threads."""

    __tablename__ = "conversations"
    __table_args__ = (
        # Listing pattern: newest conversations for an org first.
        Index("ix_conversations_org_created", "org_id", "created_at"),
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", index=True
    )
    participants: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    agent_grn: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
