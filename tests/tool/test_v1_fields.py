"""V1 Tool resource fields — execution_runtime, enabled, configuration."""
import pytest

from gabriel.tool.models import ExecutionRuntime
from gabriel.tool.repository import ToolRepository
from gabriel.tool.service import ToolService


async def _create(service, **overrides):
    fields = dict(
        org_id="acme",
        created_by="principal://acme/user/admin",
        name="calculator",
        description="Evaluates arithmetic",
        category="math",
        input_schema={},
        output_schema={},
        safety_level=0,
        required_capabilities=[],
    )
    fields.update(overrides)
    return await service.create_tool(**fields)


@pytest.mark.asyncio
async def test_new_fields_default_and_roundtrip(db_session):
    service = ToolService(ToolRepository(db_session))

    created = await _create(service)
    fetched = await service.get_tool(str(created.grn))

    assert fetched.execution_runtime == ExecutionRuntime.LOCAL
    assert fetched.enabled is True
    assert fetched.configuration == {}


@pytest.mark.asyncio
async def test_explicit_runtime_and_configuration_persist(db_session):
    service = ToolService(ToolRepository(db_session))

    created = await _create(
        service,
        execution_runtime=ExecutionRuntime.ENTERPRISE,
        enabled=False,
        configuration={"endpoint": "https://tools.internal"},
    )
    fetched = await service.get_tool(str(created.grn))

    assert fetched.execution_runtime == ExecutionRuntime.ENTERPRISE
    assert fetched.enabled is False
    assert fetched.configuration == {"endpoint": "https://tools.internal"}


@pytest.mark.asyncio
async def test_enabled_toggle_via_update(db_session):
    service = ToolService(ToolRepository(db_session))
    created = await _create(service)

    disabled = await service.update_tool(
        str(created.grn), updated_by="admin", enabled=False
    )
    assert disabled.enabled is False
    assert disabled.version == 2

    re_enabled = await service.update_tool(
        str(created.grn), updated_by="admin", enabled=True
    )
    assert re_enabled.enabled is True
    assert re_enabled.version == 3


@pytest.mark.asyncio
async def test_public_view_exposes_v1_fields(db_session):
    service = ToolService(ToolRepository(db_session))
    created = await _create(service, execution_runtime="cloud")

    view = created.public_view()
    assert view["execution_runtime"] == "cloud"
    assert view["enabled"] is True
    assert view["configuration"] == {}
