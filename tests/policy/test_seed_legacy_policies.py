from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gabriel.database.base import Base
from gabriel.policy.engine import EvaluationRequest, PolicyEngine
from gabriel.policy.repository import PolicyRepository
from gabriel.policy.service import PolicyService

import gabriel.organization.orm  # noqa: F401
import gabriel.identity.orm  # noqa: F401
import gabriel.events.orm  # noqa: F401
import gabriel.policy.orm  # noqa: F401


SEED_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "seed_legacy_policies.py"


spec = importlib.util.spec_from_file_location("seed_legacy_policies", SEED_SCRIPT_PATH)
seed_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = seed_module
spec.loader.exec_module(seed_module)


@pytest.mark.asyncio
async def test_seed_legacy_gate_policies_and_peel_tool_eval(tmp_path):
    gate_file = tmp_path / "gate.py"
    gate_file.write_text(
        "\n".join(
            [
                "ALLOW = {'principal://acme/user/alice': ['search']} ",
                "ASK = {'principal://acme/user/alice': ['webhook']} ",
                "DENY = {'*': ['dangerous']} ",
            ]
        ),
        encoding="utf-8",
    )

    db_path = tmp_path / "seed_legacy_policies.db"
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    counts = await seed_module.seed_legacy_policies(
        gate_path=gate_file,
        org_id="acme",
        created_by="principal://acme/user/admin",
        session_factory=session_factory,
    )

    assert counts == {"allow": 1, "ask": 1, "deny": 1}

    async with session_factory() as session:
        policies = await PolicyService(PolicyRepository(session)).list_policies("acme")

    assert len(policies) == 3
    policy_by_grn = {str(policy.grn): policy for policy in policies}
    assert "grn:acme:policy/legacy-gate-allow:1" in policy_by_grn
    assert "grn:acme:policy/legacy-gate-ask:1" in policy_by_grn
    assert "grn:acme:policy/legacy-gate-deny:1" in policy_by_grn

    ask_policy = policy_by_grn["grn:acme:policy/legacy-gate-ask:1"]
    assert ask_policy.statements[0].condition == "legacy:ask"

    engine_eval = PolicyEngine(policies)

    allow_decision = engine_eval.evaluate(
        EvaluationRequest(
            principal="principal://acme/user/alice",
            action="tool:invoke",
            resource="grn:acme:tool/search:1",
        )
    )
    assert allow_decision.value == "allow"

    ask_decision = engine_eval.evaluate(
        EvaluationRequest(
            principal="principal://acme/user/alice",
            action="tool:invoke",
            resource="grn:acme:tool/webhook:1",
        )
    )
    assert ask_decision.value == "deny"

    deny_decision = engine_eval.evaluate(
        EvaluationRequest(
            principal="principal://acme/user/bob",
            action="tool:invoke",
            resource="grn:acme:tool/dangerous:1",
        )
    )
    assert deny_decision.value == "deny"

    await engine.dispose()


def test_parse_legacy_gate_supports_compact_gate_dict(tmp_path):
    gate_file = tmp_path / "gate.py"
    gate_file.write_text(
        "LEGACY_GATE = {'search': 'ALLOW', 'webhook': 'ASK', 'dangerous': 'DENY'}\n",
        encoding="utf-8",
    )

    mappings = seed_module.parse_legacy_gate(gate_file)
    by_tool = {m.tool_match: m.decision for m in mappings}

    assert by_tool["search"] == "allow"
    assert by_tool["webhook"] == "ask"
    assert by_tool["dangerous"] == "deny"
