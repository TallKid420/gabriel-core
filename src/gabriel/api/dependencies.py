from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncGenerator, Any
from uuid import uuid4

from fastapi import HTTPException, Request

from gabriel.events import Command, Dispatcher, EventStore, Handler
from gabriel.events.event import Event
from gabriel.runtime.context import ExecutionContext
from gabriel.resource.grn import GRN


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
	event_store: EventStore
	dispatcher: Dispatcher
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

	def _reconstruct_resource(self, grn: str) -> dict[str, Any] | None:
		events = self.state.event_store.events_for_resource(grn)
		if not events:
			return None

		state: dict[str, Any] = {"grn": grn}
		deleted = False
		for event in events:
			if event.type in {"resource_created", "agent_created"}:
				state.update(event.payload)
				state["state"] = "active"
				deleted = False
			elif event.type in {"resource_updated", "agent_enabled", "agent_disabled"}:
				state.update(event.payload)
			elif event.type in {"resource_deleted"}:
				deleted = True
				state["state"] = "deleted"

		return None if deleted else state

	def get_resource(self, grn: str) -> dict[str, Any] | None:
		return self._reconstruct_resource(grn)

	def get_agent(self, grn: str) -> dict[str, Any] | None:
		resource = self._reconstruct_resource(grn)
		if not resource:
			return None
		if resource.get("resource_type") != "agent":
			return None
		return resource

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
		SimpleCommandHandler("execute_agent", "agent_executed"),
		SimpleCommandHandler("disable_agent", "agent_disabled"),
		SimpleCommandHandler("enable_agent", "agent_enabled"),
		SimpleCommandHandler("write_memory", "memory_written"),
		SimpleCommandHandler("delete_memory", "memory_deleted"),
	]
	for handler in handlers:
		dispatcher.register_handler(handler)


def initialize_gateway_state(app) -> None:
	event_store = EventStore()
	dispatcher = Dispatcher(event_store=event_store)
	_register_handlers(dispatcher)
	app.state.gateway_state = GatewayState(event_store=event_store, dispatcher=dispatcher)


def get_gateway_state(request: Request) -> GatewayState:
	return request.app.state.gateway_state


def get_gateway_service(request: Request) -> GatewayService:
	state = get_gateway_state(request)
	return GatewayService(state)


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

