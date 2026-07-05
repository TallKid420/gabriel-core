from __future__ import annotations

from types import SimpleNamespace

from gabriel.api.services.agents import AgentRepository, AgentService


class _StubProjection:
    def __init__(self, resources: list[dict[str, object]]) -> None:
        self.resources = resources
        self.calls: list[dict[str, object]] = []

    def list_resources(self, organization_id: str, resource_type: str | None = None, include_deleted: bool = False):
        self.calls.append(
            {
                "organization_id": organization_id,
                "resource_type": resource_type,
                "include_deleted": include_deleted,
            }
        )
        return self.resources


def test_list_available_agents_scopes_to_principal_organization():
    projection = _StubProjection(
        [
            {
                "grn": "grn:acme:agent/assistant:1",
                "organization_id": "acme",
                "state": "active",
                "attributes": {
                    "name": "Assistant",
                    "description": "Helpful agent",
                    "icon": "spark",
                    "category": "support",
                    "config": {"provider": "openai", "model": "gpt-4o-mini"},
                },
            }
        ]
    )
    service = AgentService(AgentRepository(projection))

    principal = SimpleNamespace(organization_id="acme")
    agents = service.list_available_agents(principal)

    assert projection.calls == [
        {"organization_id": "acme", "resource_type": "agent", "include_deleted": False}
    ]
    assert len(agents) == 1
    assert agents[0].id == "grn:acme:agent/assistant:1"
    assert agents[0].name == "Assistant"
    assert agents[0].description == "Helpful agent"
    assert agents[0].status == "active"
    assert agents[0].icon == "spark"
    assert agents[0].category == "support"
    assert agents[0].provider == "openai"
    assert agents[0].model == "gpt-4o-mini"
    assert agents[0].enabled is True


def test_list_available_agents_returns_empty_list_when_no_agents():
    projection = _StubProjection([])
    service = AgentService(AgentRepository(projection))

    principal = SimpleNamespace(organization_id="acme")
    agents = service.list_available_agents(principal)

    assert agents == []