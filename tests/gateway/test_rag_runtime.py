"""RAG in the chat runtime: retrieved chunks are injected into the prompt."""
from __future__ import annotations

import json

import pytest

from gabriel.agent.management import AgentManagementService
from gabriel.agent.repository import AgentRepository
from gabriel.conversation.service import ConversationService
from gabriel.events.repository import EventRepository
from gabriel.gateway.prompt import ContextBlock
from gabriel.gateway.providers.registry import ProviderRegistry
from gabriel.gateway.service import ChatRuntimeService
from gabriel.gateway.sessions import SessionManager
from gabriel.gateway.tools import build_default_tool_registry

from tests.gateway.conftest import FakeProvider

ORG = "acme"
ALICE = "alice"
SOURCE = f"grn:{ORG}:knowledge_source/src-1:1"


def parse_frames(frames: list[str]) -> list[tuple[str, dict]]:
    parsed = []
    for frame in frames:
        event, data = "", {}
        for line in frame.strip().splitlines():
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        parsed.append((event, data))
    return parsed


class FakeRetriever:
    """Stand-in for KnowledgeRetriever with a scripted response."""

    def __init__(self, blocks: list[ContextBlock] | None = None, fail: bool = False):
        self.blocks = blocks or []
        self.fail = fail
        self.calls: list[dict] = []

    async def retrieve(self, *, org_id, query, knowledge_source_grns=None, **kwargs):
        self.calls.append(
            {"org_id": org_id, "query": query, "sources": knowledge_source_grns}
        )
        if self.fail:
            # Mirrors the real retriever contract: never raises.
            return []
        return list(self.blocks)


def build_runtime(session_factory, provider, retriever) -> ChatRuntimeService:
    providers = ProviderRegistry(default_provider=provider.name)
    providers.register(provider)
    return ChatRuntimeService(
        session_factory=session_factory,
        providers=providers,
        tools=build_default_tool_registry(),
        sessions=SessionManager(),
        retriever=retriever,
    )


async def setup_conversation(session_factory, knowledge_sources) -> str:
    async with session_factory() as session:
        service = AgentManagementService(
            AgentRepository(session), EventRepository(session)
        )
        agent = await service.create_agent(
            ORG,
            "RAG agent",
            created_by=ALICE,
            system_prompt="You are Gabriel.",
            model_config={"provider": "fake", "model": "fake-model"},
            knowledge_sources=knowledge_sources,
        )
        conversation = await ConversationService(session).create_conversation(
            ORG, "RAG test", created_by=ALICE, agent_grn=str(agent.grn)
        )
        return str(conversation.grn)


async def run_turn(runtime, conversation_grn, content="What is pgvector?"):
    return parse_frames(
        [
            f
            async for f in runtime.stream_turn(
                org_id=ORG,
                principal_id=ALICE,
                conversation_grn=conversation_grn,
                content=content,
            )
        ]
    )


@pytest.mark.asyncio
async def test_retrieved_chunks_injected_into_system_prompt(session_factory):
    provider = FakeProvider(script=[{"text": "Grounded answer"}])
    retriever = FakeRetriever(
        blocks=[
            ContextBlock(
                source="knowledge:handbook.txt#chunk0",
                content="pgvector stores embeddings in PostgreSQL.",
            )
        ]
    )
    runtime = build_runtime(session_factory, provider, retriever)
    conversation_grn = await setup_conversation(session_factory, [SOURCE])

    frames = await run_turn(runtime, conversation_grn)
    events = [e for e, _ in frames]
    assert "context" in events
    context_data = next(d for e, d in frames if e == "context")
    assert context_data["chunks"] == 1
    assert context_data["sources"] == ["knowledge:handbook.txt#chunk0"]
    assert events[-1] == "done"

    # Retriever was scoped to the agent's knowledge sources.
    assert retriever.calls == [
        {"org_id": ORG, "query": "What is pgvector?", "sources": [SOURCE]}
    ]

    # The chunk text landed in the assembled system message.
    system_message = provider.calls[0]["messages"][0]
    assert system_message.role == "system"
    assert "pgvector stores embeddings in PostgreSQL." in system_message.content
    assert "knowledge:handbook.txt#chunk0" in system_message.content


@pytest.mark.asyncio
async def test_agent_without_knowledge_sources_skips_retrieval(session_factory):
    provider = FakeProvider(script=[{"text": "Plain answer"}])
    retriever = FakeRetriever(blocks=[ContextBlock(source="x", content="y")])
    runtime = build_runtime(session_factory, provider, retriever)
    conversation_grn = await setup_conversation(session_factory, [])

    frames = await run_turn(runtime, conversation_grn)
    events = [e for e, _ in frames]
    assert "context" not in events
    assert events[-1] == "done"
    assert retriever.calls == []


@pytest.mark.asyncio
async def test_empty_retrieval_does_not_break_turn(session_factory):
    provider = FakeProvider(script=[{"text": "Still fine"}])
    retriever = FakeRetriever(fail=True)
    runtime = build_runtime(session_factory, provider, retriever)
    conversation_grn = await setup_conversation(session_factory, [SOURCE])

    frames = await run_turn(runtime, conversation_grn)
    events = [e for e, _ in frames]
    assert "context" not in events
    assert "error" not in events
    assert events[-1] == "done"
    assert len(retriever.calls) == 1
