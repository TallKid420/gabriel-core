"""Tests for MemoryLayerService (Phase 2 — Core Business Logic)."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from gabriel.events.orm import EventORM
from gabriel.memory.layer_models import MemoryScope
from gabriel.memory.layer_service import MemoryLayerService
from gabriel.resource.exceptions import DuplicateResourceError, ResourceNotFoundError

pytestmark = pytest.mark.asyncio

ORG = "acme"
ACTOR = "principal-1"


async def _create(service: MemoryLayerService, key: str = "prefs.theme", **kw):
    defaults = dict(created_by=ACTOR, scope=MemoryScope.ORG)
    defaults.update(kw)
    return await service.create_entry(ORG, key, {"mode": "dark"}, **defaults)


async def test_create_entry_mints_memory_grn(db_session):
    service = MemoryLayerService(db_session)
    entry = await _create(service, tags=["ui"])

    assert str(entry.grn).startswith("grn:acme:memory/")
    assert entry.key == "prefs.theme"
    assert entry.value == {"mode": "dark"}
    assert entry.scope == MemoryScope.ORG
    assert entry.tags == ["ui"]


async def test_duplicate_key_in_namespace_rejected(db_session):
    service = MemoryLayerService(db_session)
    await _create(service)

    with pytest.raises(DuplicateResourceError):
        await _create(service)

    # Same key in a different scope namespace is fine.
    other = await _create(
        service, scope=MemoryScope.USER, subject_grn="grn:acme:user/u1:1"
    )
    assert other.subject_grn == "grn:acme:user/u1:1"


async def test_org_scoping_on_reads(db_session):
    service = MemoryLayerService(db_session)
    entry = await _create(service)

    fetched = await service.get_entry(str(entry.grn), org_id=ORG)
    assert fetched.grn == entry.grn

    with pytest.raises(ResourceNotFoundError):
        await service.get_entry(str(entry.grn), org_id="other-org")


async def test_expired_entries_hidden(db_session):
    service = MemoryLayerService(db_session)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    entry = await _create(service, expires_at=past)

    with pytest.raises(ResourceNotFoundError):
        await service.get_entry(str(entry.grn), org_id=ORG)

    entries, total = await service.list_entries(ORG)
    assert total == 0 and entries == []

    # Expired keys free their namespace slot check via get_by_key.
    assert await service.get_by_key(ORG, "prefs.theme", scope=MemoryScope.ORG) is None


async def test_list_entries_scope_and_tag_filters(db_session):
    service = MemoryLayerService(db_session)
    await _create(service, key="a", tags=["ui"])
    await _create(service, key="b", tags=["backend"])
    await _create(
        service, key="c", scope=MemoryScope.AGENT, subject_grn="grn:acme:agent/a1:1"
    )

    org_entries, org_total = await service.list_entries(ORG, scope=MemoryScope.ORG)
    assert org_total == 2

    tagged, _ = await service.list_entries(ORG, tag="ui")
    assert [e.key for e in tagged] == ["a"]

    agent_entries, agent_total = await service.list_entries(
        ORG, scope="agent", subject_grn="grn:acme:agent/a1:1"
    )
    assert agent_total == 1 and agent_entries[0].key == "c"


async def test_update_entry(db_session):
    service = MemoryLayerService(db_session)
    entry = await _create(service)

    updated = await service.update_entry(
        str(entry.grn),
        updated_by=ACTOR,
        org_id=ORG,
        value={"mode": "light"},
        tags=["ui", "prefs"],
    )
    assert updated.value == {"mode": "light"}
    assert updated.tags == ["ui", "prefs"]
    assert updated.version == entry.version + 1


async def test_delete_is_hard_but_audited(db_session):
    service = MemoryLayerService(db_session)
    entry = await _create(service)

    await service.delete_entry(str(entry.grn), deleted_by=ACTOR, org_id=ORG)

    with pytest.raises(ResourceNotFoundError):
        await service.get_entry(str(entry.grn), org_id=ORG, )

    result = await db_session.execute(
        select(EventORM).filter_by(type="resource_deleted", resource_grn=str(entry.grn))
    )
    assert len(list(result.scalars())) == 1

    # The namespace slot is free again after a hard delete.
    recreated = await _create(service)
    assert recreated.key == entry.key
