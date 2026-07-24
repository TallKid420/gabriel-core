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
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids import cycles
    from gabriel.knowledge.retrieval import KnowledgeRetriever

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gabriel.agent.grn_bindings import tool_grn
from gabriel.agent.mappers import orm_to_domain as agent_orm_to_domain
from gabriel.agent.models import Agent
from gabriel.agent.specification import AgentSpecification
from gabriel.agent.repository import AgentRepository
from gabriel.conversation.message_models import Message, MessageRole
from gabriel.conversation.message_service import ConversationClosedError, MessageService
from gabriel.conversation.models import Conversation
from gabriel.conversation.service import ConversationService
from gabriel.events.repository import EventRepository
from gabriel.gateway.approvals import ApprovalDecision, ApprovalRegistry
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
from gabriel.gateway.tools import RuntimeToolRegistry, ToolResult
from gabriel.identity.exceptions import InvalidPrincipalIDError
from gabriel.identity.models import Capability, PrincipalType
from gabriel.identity.principal import Principal
from gabriel.identity.principal_id import PrincipalID
from gabriel.logging_config import get_logger
from gabriel.policy.exceptions import UnauthorizedError
from gabriel.policy.peel import PEEL
from gabriel.resource.exceptions import ResourceNotFoundError
from gabriel.runtime.context import ExecutionContext
from gabriel.tool.exceptions import (
    ConfirmationRequiredError,
    SchemaValidationError,
    ToolInvocationError,
    ToolNotFoundError,
)
from gabriel.tool.executor import ToolExecutor
from gabriel.tool.mappers import orm_to_domain as tool_orm_to_domain
from gabriel.tool.models import SafetyLevel
from gabriel.tool.registry import FunctionRegistry
from gabriel.tool.repository import ToolRepository
from gabriel.tool.service import ToolService

logger = get_logger(__name__)

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
    allowed_tools: list[str]
    context_window: int = DEFAULT_CONTEXT_WINDOW
    knowledge_sources: tuple[str, ...] = ()
    document_collections: tuple[str, ...] = ()
    # Map of tool name -> SafetyLevel int for tools exposed this turn. Drives
    # the human-in-the-loop approval gate for REQUIRES_CONFIRMATION tools.
    tool_safety: dict[str, int] = field(default_factory=dict)

    def grounding_sources(self) -> list[str]:
        """Deduplicated GRNs used for retrieval grounding this turn."""
        seen: set[str] = set()
        combined: list[str] = []
        for grn in (*self.knowledge_sources, *self.document_collections):
            if grn not in seen:
                seen.add(grn)
                combined.append(grn)
        return combined


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
        fn_registry: FunctionRegistry,
        peel: PEEL,
        prompt_assembler: PromptAssembler | None = None,
        retriever: "KnowledgeRetriever | None" = None,
        approvals: ApprovalRegistry | None = None,
        max_tool_iterations: int = MAX_TOOL_ITERATIONS,
    ) -> None:
        self._session_factory = session_factory
        self.providers = providers
        self.tools = tools
        self.sessions = sessions
        self.fn_registry = fn_registry
        self.peel = peel
        self.prompt = prompt_assembler or PromptAssembler()
        self.retriever = retriever
        # Shared, app-wide rendezvous for human-in-the-loop tool approvals.
        self.approvals = approvals or ApprovalRegistry()
        self.max_tool_iterations = max_tool_iterations

    # ------------------------------------------------------------------
    # Human-in-the-loop approval
    # ------------------------------------------------------------------

    def submit_approval(
        self,
        *,
        session_id: str,
        tool_name: str,
        approved: bool,
        deny_reason: str | None = None,
    ) -> bool:
        """Record a user's accept/deny decision for a paused tool call.

        Returns ``True`` if a matching pending approval was found and resumed,
        ``False`` otherwise (e.g. the stream already timed out).
        """
        return self.approvals.resolve(
            session_id,
            tool_name,
            ApprovalDecision(approved=approved, deny_reason=deny_reason),
        )

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
        allowed_tools: list[str] = []
        tool_safety: dict[str, int] = {}
        knowledge_sources: tuple[str, ...] = ()
        document_collections: tuple[str, ...] = ()

        if agent_grn:
            agent = await self._load_agent(session, agent_grn, org_id)
            spec = agent.specification
            runtime_config = spec.effective_runtime_config()
            system_prompt = spec.system_prompt
            provider = provider_override or spec.provider or ""
            model = model_override or spec.model or ""
            temperature = runtime_config.temperature
            max_tokens = runtime_config.max_tokens
            # Tool exposure is opt-in (ADR-019/ADR-024): a tool is only
            # usable when it is in the discovery catalog, backed by an
            # enabled Tool resource for the org, and allowed by the agent
            # specification. See ``_resolve_allowed_tools`` for details.
            allowed_tools = await self._resolve_allowed_tools(session, spec, org_id)
            tool_safety = await self._org_tool_safety(session, org_id)
            knowledge_sources = tuple(spec.knowledge_sources or ())
            document_collections = tuple(spec.document_collections or ())

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
            tool_safety=tool_safety,
            knowledge_sources=knowledge_sources,
            document_collections=document_collections,
        )

    async def _resolve_allowed_tools(
        self, session: AsyncSession, spec: AgentSpecification, org_id: str
    ) -> list[str]:
        """Compute the runtime tool allow-list for one agent configuration.

        Opt-in governance (ADR-019/ADR-024): a tool is only exposed to the
        model when it is simultaneously —

        (A) present in the discovery catalog (:attr:`tools`, built from
            :class:`gabriel.tool.discovery.ToolLibraryIndexer`);
        (B) backed by an *enabled* ``Tool`` resource for the org (absence of
            a Tool row, or ``enabled=False``, excludes it — no more
            fail-open default);
        (C) allowed by the agent's :class:`AgentSpecification` (its declared
            tools, or every catalog/enabled tool when none are declared,
            minus anything in ``disabled_tools``).
        """
        catalog = set(self.tools.list_tools())
        enabled = await self._org_enabled_tool_names(session, org_id)
        allowed_catalog = catalog & enabled
        declared = set(spec.tool_names())
        disabled = set(spec.disabled_tool_names())
        base = declared if declared else allowed_catalog
        return sorted((base & allowed_catalog) - disabled)

    async def _org_enabled_tool_names(
        self, session: AsyncSession, org_id: str
    ) -> set[str]:
        """Names of Tool resources enabled for the org.

        Fail-secure: degrades to an empty set (no tools exposed) on lookup
        failure. Under the opt-in governance model an enabled ``Tool`` row
        is required for exposure, so an unreadable catalog must never widen
        access — it can only narrow it.
        """
        try:
            orms = await ToolRepository(session).list_for_org(org_id)
        except Exception:  # noqa: BLE001 - fail-secure: never widen access
            logger.exception(
                "Tool enablement lookup failed for org %s; "
                "no tools will be exposed this turn",
                org_id,
            )
            return set()
        return {tool_orm_to_domain(orm).name for orm in orms if orm.enabled}

    async def _org_tool_safety(
        self, session: AsyncSession, org_id: str
    ) -> dict[str, int]:
        """Map of enabled tool name -> safety level int for the org.

        Powers the human-in-the-loop approval gate: the streaming loop consults
        this map to decide whether a model-requested tool must pause for
        explicit user confirmation before dispatch. Fail-secure: on lookup
        failure returns an empty map (tools then default to SAFE handling, but
        the governed :class:`ToolExecutor` still enforces its own confirmation
        gate on dispatch).
        """
        try:
            orms = await ToolRepository(session).list_for_org(org_id)
        except Exception:  # noqa: BLE001 - fail-secure
            logger.exception("Tool safety lookup failed for org %s", org_id)
            return {}
        safety: dict[str, int] = {}
        for orm in orms:
            if not orm.enabled:
                continue
            tool = tool_orm_to_domain(orm)
            safety[tool.name] = int(tool.safety_level)
        return safety

    # ------------------------------------------------------------------
    # Governed tool execution (ADR-003 events, ADR-019 PEEL, ADR-024 schema)
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_principal_id(org_id: str, principal_id: str) -> PrincipalID:
        """Parse a GRN-style principal id, falling back to a synthetic one.

        Callers such as tests may pass a bare identifier (e.g. ``"alice"``)
        rather than the ``principal://org/type/id`` form; that is treated as
        a plain user identifier scoped to ``org_id``.
        """
        try:
            return PrincipalID.parse(principal_id)
        except InvalidPrincipalIDError:
            return PrincipalID(
                org_id=org_id,
                principal_type="user",
                principal_identifier=principal_id,
            )

    @staticmethod
    def _parse_correlation_id(correlation_id: str | None) -> UUID:
        if correlation_id:
            try:
                return UUID(correlation_id)
            except (ValueError, AttributeError):
                pass
        return uuid4()

    def _build_execution_context(
        self, *, org_id: str, principal_id: str, correlation_id: str | None
    ) -> ExecutionContext:
        """Execution context for one governed tool invocation.

        Grants exactly ``call_tool`` — the capability PEEL requires for the
        ``tool:invoke`` action (see :mod:`gabriel.policy.capabilities`) — so
        that the identity-based fallback check passes for any principal
        driving a chat turn. Org-level policy configuration (PEEL's
        policy-based branch) is still enforced regardless of this grant.
        """
        pid = self._resolve_principal_id(org_id, principal_id)
        principal = Principal(
            id=pid,
            organization_id=org_id,
            principal_type=PrincipalType.USER,
            display_name=principal_id,
            capabilities=set(),
        )
        return ExecutionContext(
            execution_id=uuid4(),
            principal=principal,
            organization=org_id,
            correlation_id=self._parse_correlation_id(correlation_id),
            causation_id=None,
            session_id=None,
            resource=None,
            started_at=datetime.now(timezone.utc),
            capabilities=frozenset({Capability.CALL_TOOL.value}),
            metadata={},
        )

    async def _invoke_tool(
        self,
        *,
        org_id: str,
        principal_id: str,
        correlation_id: str | None,
        call: ToolCallRequest,
        allowed: list[str],
        confirmed: bool = False,
    ) -> ToolResult:
        """Execute one model-requested tool call via the governed
        :class:`gabriel.tool.executor.ToolExecutor`, never raising.

        Every call is resource-addressed by GRN and cleared through PEEL,
        schema validation, and audit-event emission — the Gateway no longer
        dispatches tool callables directly (see ``execute_tool_call`` for
        the legacy, ungoverned path this replaces).
        """
        if call.name not in allowed:
            error = f"Tool '{call.name}' is not allowed for this agent."
            return ToolResult(
                tool_call_id=call.id, name=call.name,
                content=json.dumps({"error": error}), success=False, error=error,
            )

        grn = tool_grn(call.name, org_id, version=1)
        context = self._build_execution_context(
            org_id=org_id, principal_id=principal_id, correlation_id=correlation_id
        )
        try:
            async with self._session_factory() as session:
                event_repo = EventRepository(session)
                tool_service = ToolService(ToolRepository(session), event_repo)
                executor = ToolExecutor(tool_service, self.fn_registry, self.peel, event_repo)
                result = await executor.invoke(
                    context, grn, call.arguments, confirmed=confirmed
                )
            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                content=json.dumps(result, default=str),
            )
        except (
            ToolNotFoundError,
            SchemaValidationError,
            ConfirmationRequiredError,
            ToolInvocationError,
            UnauthorizedError,
        ) as exc:
            logger.exception("Governed tool '%s' failed", call.name)
            error = str(exc)
            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                content=json.dumps({"error": error}),
                success=False,
                error=error,
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

        # RAG: ground the turn in the agent's knowledge sources and document
        # collections (both are KnowledgeSource resources referenced by GRN).
        # Retrieval failures degrade to an ungrounded turn — never an error.
        grounding_sources = config.grounding_sources()
        if self.retriever is not None and grounding_sources:
            retrieved = await self.retriever.retrieve(
                org_id=org_id,
                query=content,
                knowledge_source_grns=grounding_sources,
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

                    # Human-in-the-loop gate: tools declared
                    # REQUIRES_CONFIRMATION pause the loop until the user
                    # accepts or denies via POST /gateway/chat/approval.
                    requires_confirmation = (
                        config.tool_safety.get(call.name)
                        == SafetyLevel.REQUIRES_CONFIRMATION.value
                    )
                    confirmed = False
                    denied_decision: ApprovalDecision | None = None
                    if requires_confirmation:
                        grn = tool_grn(call.name, org_id, version=1)
                        key = self.approvals.register(
                            chat_session.session_id, call.name
                        )
                        yield sse_event(
                            "tool_approval_required",
                            {
                                "id": call.id,
                                "tool_name": call.name,
                                "args": call.arguments,
                                "tool_grn": grn,
                                "session_id": chat_session.session_id,
                            },
                        )
                        decision = await self.approvals.wait(key)
                        if decision.approved:
                            confirmed = True
                        else:
                            denied_decision = decision

                    if denied_decision is not None:
                        # Deny path: skip execution and inject an informative
                        # ToolMessage so the LLM can adjust its response.
                        reason = denied_decision.deny_reason
                        denial_text = (
                            f"User denied execution of tool '{call.name}'. "
                            "The user chose not to allow this action. "
                            "Please acknowledge this and adjust your response "
                            "accordingly."
                        )
                        if reason:
                            denial_text += f" Reason provided: {reason}"
                        result = ToolResult(
                            tool_call_id=call.id,
                            name=call.name,
                            content=json.dumps(
                                {"denied": True, "message": denial_text}
                            ),
                            success=False,
                            error="denied_by_user",
                        )
                    else:
                        result = await self._invoke_tool(
                            org_id=org_id,
                            principal_id=principal_id,
                            correlation_id=correlation_id,
                            call=call,
                            allowed=config.allowed_tools,
                            confirmed=confirmed,
                        )
                    tool_call_records.append(
                        {
                            "id": call.id,
                            "name": call.name,
                            "arguments": call.arguments,
                            "success": result.success,
                            "denied": denied_decision is not None,
                        }
                    )
                    yield sse_event(
                        "tool_result",
                        {
                            "id": call.id,
                            "name": call.name,
                            "success": result.success,
                            "denied": denied_decision is not None,
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
                            "denied": denied_decision is not None,
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
