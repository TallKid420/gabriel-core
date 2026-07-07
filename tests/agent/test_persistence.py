import pytest

from gabriel.agent.repository import AgentRepository
from gabriel.agent.service import AgentService
from gabriel.agent.specification import AgentSpecification
from gabriel.resource.exceptions import ResourceNotFoundError


@pytest.mark.asyncio
async def test_agent_persists_with_specification(db_session):
    service = AgentService(AgentRepository(db_session))

    spec = AgentSpecification(
        name="assistant",
        runtime="langgraph",
        model="gpt-5.3-codex",
        system_prompt="Be precise.",
        tools=["search"],
        capabilities=["read_memory"],
        memory_layers=["session"],
        metadata={"tier": "core"},
    )

    created = await service.create_agent(
        org_id="acme",
        created_by="principal://acme/user/admin",
        specification=spec,
        agent_grn="grn:acme:agent/assistant:1",
    )

    fetched = await service.get_agent(str(created.grn))

    assert fetched.specification.name == "assistant"
    assert fetched.specification.runtime == "langgraph"
    assert fetched.specification.tools == ["search"]
    assert fetched.specification.metadata["tier"] == "core"


@pytest.mark.asyncio
async def test_agent_list_get_update_delete_crud(db_session):
    service = AgentService(AgentRepository(db_session))

    original = await service.create_agent(
        org_id="acme",
        created_by="principal://acme/user/admin",
        specification=AgentSpecification(
            name="writer",
            runtime="langgraph",
            model="gpt-5.3-codex",
        ),
        agent_grn="grn:acme:agent/writer:1",
    )

    listed = await service.list_agents("acme")
    assert len(listed) == 1
    assert str(listed[0].grn) == str(original.grn)

    updated = await service.update_agent(
        str(original.grn),
        updated_by="principal://acme/user/admin",
        specification=AgentSpecification(
            name="writer-v2",
            runtime="langgraph",
            model="gpt-5.3-codex",
            system_prompt="Use markdown.",
        ),
        enabled=False,
    )
    assert updated.specification.name == "writer-v2"
    assert updated.enabled is False
    assert updated.version == 2

    await service.delete_agent(str(original.grn), deleted_by="principal://acme/user/admin")

    with pytest.raises(ResourceNotFoundError):
        await service.get_agent(str(original.grn))
