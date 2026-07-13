"""Persistence model for the Message resource."""
from __future__ import annotations

from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from gabriel.database.base import Base, GabrielResourceMixin


class MessageORM(Base, GabrielResourceMixin):
    """Message table — turns within a conversation, append-only."""

    __tablename__ = "messages"
    __table_args__ = (
        # Listing pattern: messages of a conversation in chronological order.
        Index("ix_messages_conversation_created", "conversation_grn", "created_at"),
    )

    conversation_grn: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
