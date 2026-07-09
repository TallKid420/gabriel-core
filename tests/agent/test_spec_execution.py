"""Prove that an AgentSpecification configures agent execution (Phase 4).

This ties the migration deliverables together: a spec built from a template is
attached to an Agent, and the AgentExecutor selects the runtime declared *by the
specification* and runs it to a successful ExecutionResult.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from gabriel.agent.models import Agent
from gabriel.agent.runtime_config import RuntimeConfiguration
from gabriel.agent.templates import build_specification
from gabriel.identity.models import PrincipalType
from gabriel.identity.principal import Principal
from gabriel.identity.principal_id import PrincipalID
from gabriel.resource.grn import GRN
from gabriel.runtime.context import ExecutionContext
from gabriel.runtime.execution import AgentExecutor, ExecutionRequest
from gabriel.runtime.mock_runtime import MockRuntime
from gabriel.runtime.registry import RuntimeRegistry


def _principal(org_id: str) -> Principal:
    return Principal(
        id=PrincipalID(
            org_id=org_id,
            principal_type="user",
            principal_identifier="admin",
        ),
        organization_id=org_id,
        principal_type=PrincipalType.USER,
        display_name="Admin",
        capabilities=set(),
    )


def _context(org_id: str, spec) -> ExecutionContext:
    return ExecutionContext(
        execution_id=uuid4(),
        principal=_principal(org_id),
        organization=org_id,
        correlation_id=uuid4(),
        causation_id=None,
        session_id=None,
        resource=None,
        started_at=datetime.now(timezone.utc),
        # capabilities lowered from the spec's declared agent capabilities
        capabilities=frozenset(spec.runtime_capabilities()),
        metadata={},
    )


@pytest.mark.asyncio
async def test_specification_drives_runtime_selection() -> None:
    org_id = "acme"
    # Build from the migrated chat template, then target the mock runtime so the
    # test is hermetic. The runtime name comes from the SPEC, not the caller.
    spec = build_specification("chat").model_copy(update={"runtime": "mock"})

    agent = Agent.create(
        grn=GRN.generate(org_id=org_id, resource_type="agent"),
        org_id=org_id,
        created_by="principal://acme/user/admin",
        specification=spec,
    )

    registry = RuntimeRegistry()
    registry.register(MockRuntime())
    executor = AgentExecutor(registry)

    # NOTE: no "runtime" key in metadata -> executor falls back to
    # request.agent.specification.runtime. The spec configures execution.
    request = ExecutionRequest(
        context=_context(org_id, spec),
        agent=agent,
        input={"message": "hello"},
        metadata={},
    )

    result = await executor.execute(request)

    assert result.success is True
    assert result.output["agent"] == "hermes-chat"


def test_effective_runtime_config_reflects_spec_tuning() -> None:
    spec = build_specification("engineer")
    cfg = spec.effective_runtime_config()
    assert isinstance(cfg, RuntimeConfiguration)
    # Engineer template raises the iteration ceiling above the default (10).
    assert cfg.max_iterations == 25
    assert cfg.runtime == "langgraph"


def test_spec_without_runtime_config_defaults_to_declared_runtime() -> None:
    from gabriel.agent.specification import AgentSpecification

    spec = AgentSpecification(name="bare", runtime="mock", model="gpt-5")
    cfg = spec.effective_runtime_config()
    assert cfg.runtime == "mock"
