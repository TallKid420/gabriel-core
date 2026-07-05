from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gabriel.identity.principal import Principal
from gabriel.api.schema import ChatSummary

class ChatRepository:
    """Repository over the gateway's in-memory resource projection."""

    def __init__(self, resource_projection) -> None:
        self._resource_projection = resource_projection

    def get_chat_summary(self, organization_id: str) -> list[ChatSummary]:
        return self._resource_projection.list_resources(
            organization_id=organization_id,
            resource_type="conversations",
        )


class ChatService:
    """ Application service for chat-related operations."""

    def __init__(self, repository: ChatRepository) -> None:
        self._repository = repository

    def get_chat_summary(self, principal: Principal) -> list[ChatSummary]:
        return self._repository.get_chat_summary(principal.organization_id)