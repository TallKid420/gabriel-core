"""Tests for Core document ingestion (Document-as-Resource + ResourceCreated)."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from gabriel.document.normalizer import DocumentNormalizer, NormalizationError
from gabriel.document.service import DocumentIngestionService
from gabriel.events.dispatcher import Dispatcher
from gabriel.events.event_store import EventStore
from gabriel.identity.models import Capability, PrincipalStatus, PrincipalType
from gabriel.identity.principal import Principal
from gabriel.identity.principal_id import PrincipalID
from gabriel.policy.engine import PolicyEngine
from gabriel.policy.peel import PEEL
from gabriel.resource.models import ResourceType
from gabriel.runtime.context import ExecutionContext


def _make_context(org: str = "acme", caps=(Capability.WRITE_RESOURCE,)) -> ExecutionContext:
    principal = Principal(
        id=PrincipalID(org_id=org, principal_type="user", principal_identifier="alice"),
        organization_id=org,
        principal_type=PrincipalType.USER,
        display_name="Alice",
        status=PrincipalStatus.ACTIVE,
        capabilities=set(caps),
    )
    return ExecutionContext(
        execution_id=uuid4(),
        principal=principal,
        organization=org,
        correlation_id=uuid4(),
        causation_id=None,
        session_id=None,
        resource=None,
        started_at=datetime.now(timezone.utc),
        capabilities=frozenset(c.value for c in caps),
        metadata={},
    )


def _make_service() -> tuple[DocumentIngestionService, EventStore]:
    from gabriel.api.dependencies import _register_handlers

    store = EventStore()
    dispatcher = Dispatcher(event_store=store, peel=PEEL(PolicyEngine()))
    _register_handlers(dispatcher)
    return DocumentIngestionService(dispatcher=dispatcher), store


# --- Normalizer -----------------------------------------------------------
def test_normalizer_plaintext(tmp_path):
    f = tmp_path / "note.md"
    f.write_text("# Title\n\nHello world", encoding="utf-8")
    assert "Hello world" in DocumentNormalizer().normalize(f)


def test_normalizer_csv(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("a,b\n1,2\n", encoding="utf-8")
    out = DocumentNormalizer().normalize(f)
    assert "a, b" in out and "1, 2" in out


def test_normalizer_unsupported(tmp_path):
    f = tmp_path / "x.unknownext"
    f.write_bytes(b"\x00\x01")
    with pytest.raises(NormalizationError):
        DocumentNormalizer().normalize(f)


# --- Ingestion service ----------------------------------------------------
@pytest.mark.asyncio
async def test_ingest_creates_document_resource_and_event():
    service, store = _make_service()
    context = _make_context()

    result = await service.ingest(
        context=context,
        filename="report.txt",
        content=b"quarterly numbers",
    )

    # Document is a Resource of type DOCUMENT, tenant-scoped by GRN.
    assert result.document.resource_type == ResourceType.DOCUMENT
    assert result.document.grn.org_id == "acme"
    assert result.document.normalized_text == "quarterly numbers"
    assert result.document.content_hash is not None

    # A ResourceCreated (resource_created) event was recorded.
    assert result.event.type == "resource_created"
    events = store.events_for_resource(str(result.document.grn))
    assert len(events) == 1
    assert events[0].organization_id == "acme"


@pytest.mark.asyncio
async def test_ingest_denied_without_write_capability():
    from gabriel.policy.exceptions import UnauthorizedError

    service, _ = _make_service()
    context = _make_context(caps=(Capability.READ_RESOURCE,))

    with pytest.raises(UnauthorizedError):
        await service.ingest(context=context, filename="x.txt", content=b"hi")


@pytest.mark.asyncio
async def test_ingest_requires_exactly_one_source():
    service, _ = _make_service()
    context = _make_context()
    with pytest.raises(ValueError):
        await service.ingest(context=context, filename="x.txt")
