"""Tests for AgentManagementService (Phase 2 — Core Business Logic)."""
import pytest
from sqlalchemy import select

from gabriel.agent.management import (
    AgentManagementService,
    AgentStatus,
    ModelConfig,
    agent_public_view,
)
from gabriel.agent.repository import AgentRepository
from gabriel.events.orm import EventORM
from gabriel.events.repository import EventRepository
from gabriel.resource.exceptions import ResourceNotFoundError
from gabriel.resource.models import ResourceState

pytestmark = pytest.mark.asyncio

ORG = "acme"
ACTOR = "principal-1"


def _service(db_session) -> AgentManagementService:
    return AgentManagementService(AgentRepository(db_session), EventRepository(db_session))


async def _create(service: AgentManagementService, name: str = "support-bot", **kw):
    defaults = dict(
        created_by=ACTOR,
        description="Answers support tickets",
        system_prompt="You are a helpful support agent.",
        model_config={"provider": "openai", "model": "gpt-4o", "temperature": 0.2},
        allowed_tools=["search", "kb.lookup"],
        knowledge_sources=["grn:acme:document/d1:1"],
    )
    defaults.update(kw)
    return await service.create_agent(ORG, name, **defaults)


async def test_create_agent_maps_management_fields(db_session):
    service = _service(db_session)
    agent = await _create(service)

    assert str(agent.grn).startswith("grn:acme:agent/")
    assert agent.state == ResourceState.ACTIVE
    assert agent.enabled is True
    spec = agent.specification
    assert spec.name == "support-bot"
    assert spec.provider == "openai"
    assert spec.model == "gpt-4o"
    assert spec.tools == ["search", "kb.lookup"]
    assert spec.knowledge_sources == ["grn:acme:document/d1:1"]

    view = agent_public_view(agent)
    assert view["status"] == "active"
    assert view["model_config"]["provider"] == "openai"
    assert view["model_config"]["temperature"] == 0.2
    assert view["allowed_tools"] == ["search", "kb.lookup"]


async def test_create_draft_agent_disabled(db_session):
    service = _service(db_session)
    agent = await _create(service, name="draft-bot", status=AgentStatus.DRAFT)

    assert agent.state == ResourceState.DRAFT
    assert agent.enabled is False
    assert agent_public_view(agent)["status"] == "draft"


async def test_create_emits_resource_created_event(db_session):
    service = _service(db_session)
    agent = await _create(service)

    result = await db_session.execute(
        select(EventORM).filter_by(resource_grn=str(agent.grn), type="resource_created")
    )
    assert len(list(result.scalars())) == 1


async def test_get_agent_org_scoped(db_session):
    service = _service(db_session)
    agent = await _create(service)

    fetched = await service.get_agent(str(agent.grn), org_id=ORG)
    assert fetched.grn == agent.grn

    with pytest.raises(ResourceNotFoundError):
        await service.get_agent(str(agent.grn), org_id="other-org")


async def test_list_agents_paginated(db_session):
    service = _service(db_session)
    for i in range(3):
        await _create(service, name=f"bot-{i}")

    page, total = await service.list_agents(ORG, limit=2, offset=0)
    assert total == 3
    assert len(page) == 2


async def test_update_agent_fields_and_status(db_session):
    service = _service(db_session)
    agent = await _create(service)

    updated = await service.update_agent(
        str(agent.grn),
        updated_by=ACTOR,
        org_id=ORG,
        description="Updated description",
        model_config=ModelConfig(provider="anthropic", model="claude-3", temperature=0.7),
        allowed_tools=["search"],
        status=AgentStatus.INACTIVE,
    )

    spec = updated.specification
    assert spec.description == "Updated description"
    assert spec.provider == "anthropic"
    assert spec.model == "claude-3"
    assert spec.tools == ["search"]
    assert updated.state == ResourceState.SUSPENDED
    assert updated.enabled is False
    assert updated.version == agent.version + 1


async def test_delete_agent(db_session):
    service = _service(db_session)
    agent = await _create(service)

    await service.delete_agent(str(agent.grn), deleted_by=ACTOR, org_id=ORG)

    with pytest.raises(ResourceNotFoundError):
        await service.get_agent(str(agent.grn), org_id=ORG)

    result = await db_session.execute(
        select(EventORM).filter_by(resource_grn=str(agent.grn), type="resource_deleted")
    )
    assert len(list(result.scalars())) == 1
