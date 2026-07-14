"""ChatRuntimeService — end-to-end chat orchestration (Phase 3).

The Gateway's core loop. For one user turn it:

1. resolves the conversation (tenant-scoped) and its configured agent;
2. opens/refreshes an ephemeral :class:`ChatSession`;
3. persists the user message (Phase-2 MessageService — durable record);
4. assembles the prompt (system prompt + windowed history + new turn);
5. streams the completion from the agent's configured LLM provider;
6. executes tools when the model requests them, feeding results back as
   ``tool``-role messages and looping (bounded by ``max_tool_iterations``);
7. persists the assistant response with token accounting;
8. emits SSE events throughout (``session`` → ``token``* → ``tool_call`` /
   ``tool_result``* → ``done`` | ``error``).

The Gateway owns no persistent business data: every durable write goes
through the Phase-2 conversation/message services.
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids import cycles
    from gabriel.knowledge.retrieval import KnowledgeRetriever

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gabriel.agent.mappers import orm_to_domain as agent_orm_to_domain
from gabriel.agent.models import Agent
from gabriel.agent.repository import AgentRepository
from gabriel.conversation.message_models import Message, MessageRole
from gabriel.conversation.message_service import ConversationClosedError, MessageService
from gabriel.conversation.models import Conversation
from gabriel.conversation.service import ConversationService
from gabriel.gateway.prompt import DEFAULT_CONTEXT_WINDOW, ContextBlock, PromptAssembler
from gabriel.gateway.providers.base import (
    ChatMessage,
    ProviderError,
    StreamChunk,
    TokenUsage,
    ToolCallRequest,
)
from gabriel.gateway.providers.registry import ProviderRegistry
from gabriel.gateway.sessions import SessionManager
from gabriel.gateway.tools import RuntimeToolRegistry, execute_tool_call
from gabriel.resource.exceptions import ResourceNotFoundError

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 4


class ChatRuntimeError(Exception):
    """Non-provider runtime failure (bad conversation, disabled agent, …)."""


@dataclass(frozen=True)
class AgentRuntimeConfig:
    """Resolved per-turn LLM routing configuration."""

    agent_grn: str | None
    system_prompt: str
    provider: str
    model: str
    temperature: float
    max_tokens: int | None
    allowed_tools: list[str] | None
    context_window: int = DEFAULT_CONTEXT_WINDOW
    knowledge_sources: tuple[str, ...] = ()


def sse_event(event: str, data: dict[str, Any]) -> str:
    """Format one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


class ChatRuntimeService:
    """Orchestrates streaming chat turns across providers, tools & storage."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        providers: ProviderRegistry,
        tools: RuntimeToolRegistry,
        sessions: SessionManager,
        prompt_assembler: PromptAssembler | None = None,
        retriever: "KnowledgeRetriever | None" = None,
        max_tool_iterations: int = MAX_TOOL_ITERATIONS,
    ) -> None:
        self._session_factory = session_factory
        self.providers = providers
        self.tools = tools
        self.sessions = sessions
        self.prompt = prompt_assembler or PromptAssembler()
        self.retriever = retriever
        self.max_tool_iterations = max_tool_iterations

    # ------------------------------------------------------------------
    # Configuration resolution
    # ------------------------------------------------------------------

    async def _load_conversation(
        self, session: AsyncSession, conversation_grn: str, org_id: str
    ) -> Conversation:
        try:
            return await ConversationService(session).get_conversation(
                conversation_grn, org_id=org_id
            )
        except ResourceNotFoundError as exc:
            raise ChatRuntimeError(
                f"Conversation {conversation_grn} not found"
            ) from exc

    async def _load_agent(
        self, session: AsyncSession, agent_grn: str, org_id: str
    ) -> Agent:
        try:
            orm = await AgentRepository(session).get_by_grn(agent_grn)
        except ResourceNotFoundError as exc:
            raise ChatRuntimeError(f"Agent {agent_grn} not found") from exc
        agent = agent_orm_to_domain(orm)
        if agent.org_id != org_id:
            raise ChatRuntimeError(f"Agent {agent_grn} not found")
        if not agent.enabled:
            raise ChatRuntimeError(f"Agent {agent_grn} is disabled")
        return agent

    async def resolve_config(
        self,
        session: AsyncSession,
        *,
        conversation: Conversation,
        org_id: str,
        model_override: str | None = None,
        provider_override: str | None = None,
    ) -> AgentRuntimeConfig:
        """Config-driven provider/model selection for this conversation."""
        agent_grn = conversation.agent_grn
        system_prompt = ""
        provider = provider_override or ""
        model = model_override or ""
        temperature = 0.0
        max_tokens: int | None = None
        allowed_tools: list[str] | None = None
        knowledge_sources: tuple[str, ...] = ()

        if agent_grn:
            agent = await self._load_agent(session, agent_grn, org_id)
            spec = agent.specification
            runtime_config = spec.effective_runtime_config()
            system_prompt = spec.system_prompt
            provider = provider_override or spec.provider or ""
            model = model_override or spec.model or ""
            temperature = runtime_config.temperature
            max_tokens = runtime_config.max_tokens
            # An agent that declares tools is restricted to them; an agent
            # with no declared tools may use every registered runtime tool.
            allowed_tools = spec.tool_names() or None
            knowledge_sources = tuple(spec.knowledge_sources or ())

        if not model:
            raise ChatRuntimeError(
                "No model configured: the conversation's agent declares no "
                "model and no 'model' override was provided."
            )
        return AgentRuntimeConfig(
            agent_grn=agent_grn,
            system_prompt=system_prompt,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            allowed_tools=allowed_tools,
            knowledge_sources=knowledge_sources,
        )

    # ------------------------------------------------------------------
    # Persistence helpers (durable writes go through Phase-2 services)
    # ------------------------------------------------------------------

    async def _persist_message(
        self,
        *,
        conversation_grn: str,
        org_id: str,
        created_by: str,
        role: MessageRole,
        content: str,
        usage: TokenUsage | None = None,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> Message:
        async with self._session_factory() as session:
            return await MessageService(session).create_message(
                conversation_grn,
                org_id=org_id,
                created_by=created_by,
                role=role,
                content=content,
                prompt_tokens=usage.prompt_tokens if usage else None,
                completion_tokens=usage.completion_tokens if usage else None,
                total_tokens=usage.total_tokens if usage else None,
                model=model,
                metadata=metadata,
                correlation_id=correlation_id,
            )

    async def _history(
        self, conversation_grn: str, org_id: str, *, window: int
    ) -> list[Message]:
        async with self._session_factory() as session:
            service = MessageService(session)
            _, total = await service.list_messages(
                conversation_grn, org_id=org_id, limit=1, offset=0
            )
            offset = max(total - window, 0)
            items, _ = await service.list_messages(
                conversation_grn, org_id=org_id, limit=window, offset=offset
            )
            return items

    # ------------------------------------------------------------------
    # Streaming turn
    # ------------------------------------------------------------------

    async def stream_turn(
        self,
        *,
        org_id: str,
        principal_id: str,
        conversation_grn: str,
        content: str,
        model_override: str | None = None,
        provider_override: str | None = None,
        context_blocks: list[ContextBlock] | None = None,
        correlation_id: str | None = None,
    ) -> AsyncIterator[str]:
        """Run one chat turn, yielding SSE frames.

        Never raises mid-stream: failures surface as ``error`` events so the
        client connection terminates cleanly.
        """
        try:
            async with self._session_factory() as session:
                conversation = await self._load_conversation(
                    session, conversation_grn, org_id
                )
                config = await self.resolve_config(
                    session,
                    conversation=conversation,
                    org_id=org_id,
                    model_override=model_override,
                    provider_override=provider_override,
                )
            provider = self.providers.resolve(config.provider or None)
        except (ChatRuntimeError, ProviderError) as exc:
            yield sse_event("error", {"detail": str(exc)})
            return

        chat_session = self.sessions.get_or_create(
            org_id=org_id,
            principal_id=principal_id,
            conversation_grn=conversation_grn,
            agent_grn=config.agent_grn,
            provider=provider.name,
            model=config.model,
        )
        yield sse_event(
            "session",
            {
                "session_id": chat_session.session_id,
                "conversation_grn": conversation_grn,
                "agent_grn": config.agent_grn,
                "provider": provider.name,
                "model": config.model,
            },
        )

        # History *before* this turn; the new content rides as user_content.
        history = await self._history(
            conversation_grn, org_id, window=config.context_window
        )

        try:
            user_message = await self._persist_message(
                conversation_grn=conversation_grn,
                org_id=org_id,
                created_by=principal_id,
                role=MessageRole.USER,
                content=content,
                correlation_id=correlation_id,
            )
        except (ConversationClosedError, ResourceNotFoundError) as exc:
            yield sse_event("error", {"detail": str(exc)})
            return
        yield sse_event("message", {"grn": str(user_message.grn), "role": "user"})

        # RAG: ground the turn in the agent's knowledge sources (Phase 4).
        # Retrieval failures degrade to an ungrounded turn — never an error.
        if self.retriever is not None and config.knowledge_sources:
            retrieved = await self.retriever.retrieve(
                org_id=org_id,
                query=content,
                knowledge_source_grns=list(config.knowledge_sources),
            )
            if retrieved:
                context_blocks = list(context_blocks or []) + retrieved
                yield sse_event(
                    "context",
                    {
                        "chunks": len(retrieved),
                        "sources": [block.source for block in retrieved],
                    },
                )

        messages = self.prompt.assemble(
            system_prompt=config.system_prompt,
            history=history,
            user_content=content,
            context_blocks=context_blocks,
            context_window=config.context_window,
        )
        tool_specs = self.tools.llm_specs(allowed=config.allowed_tools)

        answer_parts: list[str] = []
        usage = TokenUsage()
        finish_reason: str | None = None
        tool_call_records: list[dict[str, Any]] = []

        try:
            for _ in range(self.max_tool_iterations + 1):
                pending_calls: tuple[ToolCallRequest, ...] = ()
                iteration_text: list[str] = []

                stream = provider.stream_chat_completion(
                    messages,
                    model=config.model,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                    tools=tool_specs or None,
                )
                async for chunk in stream:
                    if chunk.delta:
                        iteration_text.append(chunk.delta)
                        answer_parts.append(chunk.delta)
                        yield sse_event("token", {"delta": chunk.delta})
                    if chunk.tool_calls:
                        pending_calls += chunk.tool_calls
                    if chunk.done:
                        finish_reason = chunk.finish_reason or "stop"
                        if chunk.usage is not None:
                            usage = TokenUsage(
                                prompt_tokens=usage.prompt_tokens
                                + chunk.usage.prompt_tokens,
                                completion_tokens=usage.completion_tokens
                                + chunk.usage.completion_tokens,
                            )

                if not pending_calls:
                    break

                # Feed the model's tool request + results back into the loop.
                messages.append(
                    ChatMessage(role="assistant", content="".join(iteration_text))
                )
                for call in pending_calls:
                    yield sse_event(
                        "tool_call",
                        {"id": call.id, "name": call.name, "arguments": call.arguments},
                    )
                    result = await execute_tool_call(
                        self.tools, call, allowed=config.allowed_tools
                    )
                    tool_call_records.append(
                        {
                            "id": call.id,
                            "name": call.name,
                            "arguments": call.arguments,
                            "success": result.success,
                        }
                    )
                    yield sse_event(
                        "tool_result",
                        {
                            "id": call.id,
                            "name": call.name,
                            "success": result.success,
                            "content": result.content,
                        },
                    )
                    messages.append(
                        ChatMessage(
                            role="tool",
                            content=result.content,
                            name=result.name,
                            tool_call_id=result.tool_call_id,
                        )
                    )
                    # Durable audit trail of the tool exchange.
                    await self._persist_message(
                        conversation_grn=conversation_grn,
                        org_id=org_id,
                        created_by=principal_id,
                        role=MessageRole.TOOL,
                        content=result.content,
                        metadata={
                            "tool_name": call.name,
                            "tool_call_id": call.id,
                            "success": result.success,
                        },
                        correlation_id=correlation_id,
                    )
            else:
                logger.warning(
                    "Tool loop exhausted after %s iterations for %s",
                    self.max_tool_iterations,
                    conversation_grn,
                )
        except ProviderError as exc:
            yield sse_event("error", {"detail": str(exc)})
            return

        answer = "".join(answer_parts)
        assistant_message = await self._persist_message(
            conversation_grn=conversation_grn,
            org_id=org_id,
            created_by=config.agent_grn or principal_id,
            role=MessageRole.ASSISTANT,
            content=answer,
            usage=usage,
            model=config.model,
            metadata={"provider": provider.name, "tool_calls": tool_call_records},
            correlation_id=correlation_id,
        )
        chat_session.record_turn(tokens=usage.total_tokens)

        yield sse_event(
            "done",
            {
                "message_grn": str(assistant_message.grn),
                "conversation_grn": conversation_grn,
                "session_id": chat_session.session_id,
                "model": config.model,
                "provider": provider.name,
                "finish_reason": finish_reason or "stop",
                "usage": {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                },
            },
        )

    # ------------------------------------------------------------------
    # Non-streaming turn (same pipeline, buffered)
    # ------------------------------------------------------------------

    async def complete_turn(
        self,
        *,
        org_id: str,
        principal_id: str,
        conversation_grn: str,
        content: str,
        model_override: str | None = None,
        provider_override: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Run one turn and return the final payload (no SSE)."""
        final: dict[str, Any] | None = None
        error: dict[str, Any] | None = None
        answer_parts: list[str] = []
        async for frame in self.stream_turn(
            org_id=org_id,
            principal_id=principal_id,
            conversation_grn=conversation_grn,
            content=content,
            model_override=model_override,
            provider_override=provider_override,
            correlation_id=correlation_id,
        ):
            event, data = _parse_sse(frame)
            if event == "token":
                answer_parts.append(data.get("delta", ""))
            elif event == "done":
                final = data
            elif event == "error":
                error = data
        if error is not None:
            raise ChatRuntimeError(error.get("detail", "chat turn failed"))
        assert final is not None  # stream always ends with done or error
        final["content"] = "".join(answer_parts)
        return final


def _parse_sse(frame: str) -> tuple[str, dict[str, Any]]:
    """Parse one SSE frame produced by :func:`sse_event`."""
    event = ""
    data: dict[str, Any] = {}
    for line in frame.strip().splitlines():
        if line.startswith("event: "):
            event = line[len("event: "):]
        elif line.startswith("data: "):
            data = json.loads(line[len("data: "):])
    return event, data
