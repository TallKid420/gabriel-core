from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gabriel.database.base import Base
from gabriel.events.audit import PeelEvaluationEvent
from gabriel.events.projections.audit_projection import AuditProjection

import gabriel.organization.orm  # noqa: F401
import gabriel.identity.orm  # noqa: F401
import gabriel.events.orm  # noqa: F401
import gabriel.events.projections.audit_projection  # noqa: F401


@pytest.mark.asyncio
async def test_audit_projection_persists_and_queries_by_filters(tmp_path):
    db_path = tmp_path / "audit_projection.db"
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    projection = AuditProjection(session_factory)
    now = datetime.now(timezone.utc)

    await projection.handle_event(
        PeelEvaluationEvent(
            principal_id="principal://acme/user/alice",
            organization_id="acme",
            resource_grn="grn:acme:tool/search:1",
            occurred_at=now - timedelta(minutes=3),
            payload={"decision": "allow", "action": "tool:invoke"},
        )
    )
    await projection.handle_event(
        PeelEvaluationEvent(
            principal_id="principal://acme/user/bob",
            organization_id="acme",
            resource_grn="grn:acme:tool/search:1",
            occurred_at=now - timedelta(minutes=2),
            payload={"decision": "deny", "action": "tool:invoke"},
        )
    )
    await projection.handle_event(
        PeelEvaluationEvent(
            principal_id="principal://acme/user/alice",
            organization_id="acme",
            resource_grn="grn:acme:tool/webhook:1",
            occurred_at=now - timedelta(minutes=1),
            payload={"decision": "allow", "action": "tool:invoke"},
        )
    )

    by_principal = await projection.query(principal_id="principal://acme/user/alice", organization_id="acme")
    assert len(by_principal) == 2
    assert all(event.principal_id == "principal://acme/user/alice" for event in by_principal)

    by_decision = await projection.query(decision="deny", organization_id="acme")
    assert len(by_decision) == 1
    assert by_decision[0].payload["decision"] == "deny"

    by_time = await projection.query(
        start_time=now - timedelta(minutes=2, seconds=30),
        end_time=now - timedelta(seconds=30),
        organization_id="acme",
    )
    assert len(by_time) == 2

    await engine.dispose()
