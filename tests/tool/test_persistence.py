import pytest

from gabriel.resource.bootstrap import register_core_resource_types
from gabriel.tool.repository import ToolRepository
from gabriel.tool.service import ToolService
from gabriel.resource.exceptions import ResourceNotFoundError


@pytest.mark.asyncio
async def test_tool_persists_with_full_schema(db_session):
    service = ToolService(ToolRepository(db_session))

    created = await service.create_tool(
        org_id="acme",
        created_by="principal://acme/user/admin",
        tool_grn="grn:acme:tool/search:1",
        name="search",
        description="Searches indexed docs",
        category="retrieval",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"results": {"type": "array"}}},
        safety_level=2,
        required_capabilities=["call_tool"],
    )

    fetched = await service.get_tool(str(created.grn))

    assert fetched.name == "search"
    assert fetched.category == "retrieval"
    assert fetched.input_schema["properties"]["query"]["type"] == "string"
    assert fetched.required_capabilities == ["call_tool"]


@pytest.mark.asyncio
async def test_tool_list_get_update_delete_crud(db_session):
    service = ToolService(ToolRepository(db_session))

    created = await service.create_tool(
        org_id="acme",
        created_by="principal://acme/user/admin",
        tool_grn="grn:acme:tool/summarize:1",
        name="summarize",
        description="Summarizes text",
        category="nlp",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        safety_level=1,
        required_capabilities=["call_tool"],
    )

    listed = await service.list_tools("acme")
    assert len(listed) == 1
    assert str(listed[0].grn) == str(created.grn)

    updated = await service.update_tool(
        str(created.grn),
        updated_by="principal://acme/user/admin",
        description="Summarizes long text",
        safety_level=3,
        required_capabilities=["call_tool", "read_resource"],
    )

    assert updated.description == "Summarizes long text"
    assert updated.safety_level == 3
    assert updated.version == 2
    assert updated.required_capabilities == ["call_tool", "read_resource"]

    await service.delete_tool(
        str(created.grn),
        deleted_by="principal://acme/user/admin",
    )

    with pytest.raises(ResourceNotFoundError):
        await service.get_tool(str(created.grn))


def test_bootstrap_registers_tool_descriptor():
    from gabriel.resource.registry import ResourceRegistry

    reg = ResourceRegistry()
    register_core_resource_types(reg)

    descriptor = reg.get_descriptor("tool")
    assert descriptor is not None
    assert descriptor.type_name == "tool"
    assert "tool:create" in descriptor.capabilities
