from __future__ import annotations

import asyncio
from pathlib import Path
from dataclasses import dataclass, field
from typing import AsyncGenerator, Any
from uuid import uuid4

from fastapi import HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gabriel.events import Command, Dispatcher, EventStore, Handler
from gabriel.events.event import Event
from gabriel.events.resource_projection import ResourceReadModelProjection
from gabriel.events.sql_event_store import SqlAlchemyEventStore
from gabriel.document.content_store import DiskContentStore
from gabriel.database.base import Base
from gabriel.database.session import async_session, engine

from gabriel.api.services.agents import AgentRepository, AgentService
from gabriel.api.services.chat import ChatService, ChatRepository
from gabriel.api.services.notification import NotificationService, NotificationRepository

from gabriel.policy.engine import PolicyEngine
from gabriel.policy.peel import PEEL
from gabriel.runtime.context import ExecutionContext
from gabriel.resource.grn import GRN
import gabriel.events.orm  # noqa: F401
import gabriel.resource.read_model_orm  # noqa: F401


class SimpleCommandHandler(Handler):
        def __init__(self, command_type: str, event_type: str):
                self._command_type = command_type
                self._event_type = event_type

        @property
        def command_type(self) -> str:
                return self._command_type

        async def handle(self, command: Command) -> list[Event]:
                payload = dict(command.payload)
                resource_grn = command.target_resource_grn or payload.get("grn")

                if command.type in {"create_resource", "create_agent"} and not resource_grn:
                        org_id = command.organization_id
                        resource_type = payload.get("resource_type") or "resource"
                        resource_id = payload.get("resource_id") or str(uuid4())
                        resource_grn = str(
                                GRN(
                                        org_id=org_id,
                                        resource_type=resource_type,
                                        resource_id=resource_id,
                                        version=int(payload.get("version", 1)),
                                )
                        )
                        payload["grn"] = resource_grn

                event = Event(
                        type=self._event_type,
                        principal_id=command.principal_id,
                        organization_id=command.organization_id,
                        resource_grn=resource_grn,
                        correlation_id=command.correlation_id,
                        payload=payload,
                        metadata=command.metadata,
                )
                return [event]


@dataclass
class GatewayState:
        event_store: EventStore | SqlAlchemyEventStore
        dispatcher: Dispatcher
        peel: PEEL
        resource_projection: ResourceReadModelProjection
        memory_entries: dict[str, dict[str, Any]] = field(default_factory=dict)


class GatewayService:
        def __init__(self, state: GatewayState):
                self.state = state

        async def dispatch_command(self, command: Command, context: ExecutionContext) -> list[Event]:
                return await self.state.dispatcher.dispatch(command=command, context=context)

        def list_events(self) -> list[Event]:
                return self.state.event_store.events()

        def get_event(self, event_id: str) -> Event | None:
                for event in self.state.event_store.events():
                        if event.id == event_id:
                                return event
                return None

        def get_resource(self, grn: str) -> dict[str, Any] | None:
                return self.state.resource_projection.get_resource(grn)

        def get_agent(self, grn: str) -> dict[str, Any] | None:
                resource = self.state.resource_projection.get_resource(grn)
                if not resource:
                        return None
                if resource.get("resource_type") != "agent":
                        return None
                return resource

        def list_resources(
                self,
                organization_id: str,
                resource_type: str | None = None,
                include_deleted: bool = False,
        ) -> list[dict[str, Any]]:
                return self.state.resource_projection.list_resources(
                        organization_id=organization_id,
                        resource_type=resource_type,
                        include_deleted=include_deleted,
                )

        def list_memory(self, organization_id: str) -> list[dict[str, Any]]:
                return [
                        value
                        for value in self.state.memory_entries.values()
                        if value.get("organization_id") == organization_id
                ]

        def create_memory_entry(self, organization_id: str, content: Any, metadata: dict[str, Any]) -> dict[str, Any]:
                memory_id = str(uuid4())
                entry = {
                        "id": memory_id,
                        "organization_id": organization_id,
                        "content": content,
                        "metadata": metadata,
                }
                self.state.memory_entries[memory_id] = entry
                return entry

        def delete_memory_entry(self, memory_id: str) -> bool:
                return self.state.memory_entries.pop(memory_id, None) is not None


class EventStreamer:
    """Translates internal Dispatcher events into SSE-formatted strings."""

    def __init__(self, dispatcher: Dispatcher):
        self.dispatcher = dispatcher

    async def stream_events(self, organization_id: str) -> AsyncGenerator[str, None]:
        queue = self.dispatcher.subscribe()
        try:
            while True:
                event: Event = await queue.get()
                if event.organization_id == organization_id:
                    yield f"data: {event.model_dump_json()}\n\n"
        finally:
            self.dispatcher.unsubscribe(queue)


def get_current_context(request: Request) -> ExecutionContext:
    """Alias for get_execution_context — used by streaming endpoints."""
    return get_execution_context(request)


def get_event_streamer(request: Request) -> EventStreamer:
    """Provides an EventStreamer backed by the app's Dispatcher."""
    state = get_gateway_state(request)
    return EventStreamer(state.dispatcher)


def _register_handlers(dispatcher: Dispatcher) -> None:
        handlers = [
                SimpleCommandHandler("create_resource", "resource_created"),
                SimpleCommandHandler("update_resource", "resource_updated"),
                SimpleCommandHandler("delete_resource", "resource_deleted"),
                SimpleCommandHandler("create_agent", "agent_created"),
                SimpleCommandHandler("delete_agent", "agent_deleted"),
                SimpleCommandHandler("execute_agent", "agent_executed"),
                SimpleCommandHandler("disable_agent", "agent_disabled"),
                SimpleCommandHandler("enable_agent", "agent_enabled"),
                SimpleCommandHandler("write_memory", "memory_written"),
                SimpleCommandHandler("delete_memory", "memory_deleted"),
        ]
        for handler in handlers:
                dispatcher.register_handler(handler)


async def _build_persisted_event_store() -> SqlAlchemyEventStore:
        try:
                async with engine.begin() as conn:
                        await conn.run_sync(Base.metadata.create_all)
                return await SqlAlchemyEventStore.load_from_db(async_session)
        except (SQLAlchemyError, OSError, ConnectionError):
                data_dir = Path(".gabriel")
                data_dir.mkdir(parents=True, exist_ok=True)
                fallback_engine = create_async_engine(
                        "sqlite+aiosqlite:///./.gabriel/gateway_events.db",
                        echo=False,
                )
                fallback_session = async_sessionmaker(
                        fallback_engine,
                        expire_on_commit=False,
                        class_=AsyncSession,
                )
                async with fallback_engine.begin() as conn:
                        await conn.run_sync(Base.metadata.create_all)
                return await SqlAlchemyEventStore.load_from_db(fallback_session)


async def initialize_gateway_state(app) -> None:
    event_store = await _build_persisted_event_store()

    peel = PEEL(PolicyEngine())
    dispatcher = Dispatcher(event_store=event_store, peel=peel)
    _register_handlers(dispatcher)

    projection_session_factory = (
        event_store.session_factory
        if hasattr(event_store, "session_factory")
        else async_session
    )

    resource_projection = ResourceReadModelProjection(projection_session_factory)
    dispatcher.register_projection(resource_projection)

    await resource_projection.bootstrap()

    if await resource_projection.is_empty() and event_store.events():
        await dispatcher.replay_events(event_store.events())

    app.state.gateway_state = GatewayState(
        event_store=event_store,
        dispatcher=dispatcher,
        peel=peel,
        resource_projection=resource_projection,
    )

    app.state.peel = peel


def get_gateway_state(request: Request) -> GatewayState:
        return request.app.state.gateway_state


def get_gateway_service(request: Request) -> GatewayService:
        state = get_gateway_state(request)
        return GatewayService(state)


def get_agent_service(request: Request) -> AgentService:
        state = get_gateway_state(request)
        return AgentService(AgentRepository(state.resource_projection))

def get_chat_service(request: Request) -> ChatService:
        state = get_gateway_state(request)
        return ChatService(ChatRepository(state.resource_projection))

def get_notification_service(request: Request) -> NotificationService:
        state = get_gateway_state(request)
        return NotificationService(NotificationRepository(state.resource_projection))

def get_document_ingestion_service(request: Request):
        """Provide a DocumentIngestionService backed by the app Dispatcher."""
        from gabriel.document.service import DocumentIngestionService

        state = get_gateway_state(request)
        return DocumentIngestionService(
                dispatcher=state.dispatcher,
                content_store=DiskContentStore(Path(".gabriel/content")),
        )


def get_execution_context(request: Request) -> ExecutionContext:
        context = getattr(request.state, "execution_context", None)
        if context is None:
                raise HTTPException(status_code=401, detail="Unauthorized")
        return context


def build_command(
        context: ExecutionContext,
        command_type: str,
        payload: dict[str, Any],
        *,
        action_name: str | None = None,
        target_resource_grn: str | None = None,
) -> Command:
        return Command(
                type=command_type,
                principal_id=str(context.principal.id),
                organization_id=context.organization,
                action_name=action_name,
                target_resource_grn=target_resource_grn,
                correlation_id=str(context.correlation_id),
                payload=payload,
                metadata={"execution_id": str(context.execution_id), **context.metadata},
        )

