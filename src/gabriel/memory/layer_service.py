"""Memory layer entry service.

Org-scoped CRUD for governed memory metadata entries (Universal Resources).
Key uniqueness is enforced per (org, scope, subject) namespace; expired
entries behave as if they do not exist. Deletions are hard deletes — memory
purges must actually remove data — but the deletion *event* is preserved in
the event store for auditability.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gabriel.events.event import Event
from gabriel.events.repository import EventRepository
from gabriel.memory.layer_mappers import domain_to_orm, orm_to_domain
from gabriel.memory.layer_models import MemoryLayerEntry, MemoryScope
from gabriel.memory.layer_repository import MemoryLayerRepository
from gabriel.resource.bootstrap import register_core_resource_types
from gabriel.resource.exceptions import DuplicateResourceError
from gabriel.resource.factory import ResourceFactory
from gabriel.resource.grn import GRN
from gabriel.resource.models import ResourceState
from gabriel.resource.registry import registry


def _normalize_scope(scope: MemoryScope | str) -> MemoryScope:
    return scope if isinstance(scope, MemoryScope) else MemoryScope(scope)


class MemoryLayerService:
    """Business logic for memory layer entries (org-scoped)."""

    def __init__(self, session: AsyncSession, event_repo: EventRepository | None = None):
        register_core_resource_types()
        self.session = session
        self.repo = MemoryLayerRepository(session)
        self.event_repo = event_repo or EventRepository(session)
        self.factory = ResourceFactory(registry)

    async def create_entry(
        self,
        org_id: str,
        key: str,
        value: Any,
        *,
        created_by: str,
        scope: MemoryScope | str = MemoryScope.ORG,
        subject_grn: str | None = None,
        tags: list[str] | None = None,
        expires_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        commit: bool = True,
    ) -> MemoryLayerEntry:
        """Create an entry; the key must be free within its namespace."""
        normalized_scope = _normalize_scope(scope)
        existing = await self.repo.find_by_key(
            org_id, key, scope=normalized_scope.value, subject_grn=subject_grn
        )
        if existing is not None:
            raise DuplicateResourceError(
                f"Memory key '{key}' already exists in scope "
                f"'{normalized_scope.value}' for organization '{org_id}'"
            )

        grn = GRN.generate(org_id=org_id, resource_type="memory")
        entry: MemoryLayerEntry = self.factory.create(
            "memory_layer_entry",
            grn=grn,
            org_id=org_id,
            state=ResourceState.ACTIVE,
            created_by=created_by,
            updated_by=created_by,
            key=key,
            value=value,
            scope=normalized_scope,
            subject_grn=subject_grn,
            tags=tags or [],
            expires_at=expires_at,
            metadata=metadata or {},
        )
        try:
            orm = await self.repo.create(domain_to_orm(entry))
        except IntegrityError as exc:
            await self.session.rollback()
            raise DuplicateResourceError(
                f"Memory key '{key}' conflicts with an existing entry"
            ) from exc
        await self.event_repo.append(
            Event(
                type="resource_created",
                principal_id=created_by,
                organization_id=org_id,
                resource_grn=str(grn),
                correlation_id=correlation_id,
                payload={
                    "resource_type": "memory",
                    "grn": str(grn),
                    "key": key,
                    "scope": normalized_scope.value,
                    "subject_grn": subject_grn,
                },
                metadata={"service": "MemoryLayerService", "operation": "create_entry"},
            )
        )
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return orm_to_domain(orm)

    async def get_entry(self, grn_str: str, org_id: str | None = None) -> MemoryLayerEntry:
        return orm_to_domain(await self.repo.get_by_grn(grn_str, org_id=org_id))

    async def get_by_key(
        self,
        org_id: str,
        key: str,
        *,
        scope: MemoryScope | str | None = None,
        subject_grn: str | None = None,
    ) -> MemoryLayerEntry | None:
        scope_value = _normalize_scope(scope).value if scope is not None else None
        orm = await self.repo.find_by_key(
            org_id, key, scope=scope_value, subject_grn=subject_grn
        )
        return orm_to_domain(orm) if orm else None

    async def list_entries(
        self,
        org_id: str,
        *,
        scope: MemoryScope | str | None = None,
        subject_grn: str | None = None,
        tag: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MemoryLayerEntry], int]:
        """Paginated org-scoped listing; returns (items, total).

        ``tag`` filtering is applied post-query (JSON list column) — the page
        is filtered, so a tag-filtered page may be shorter than ``limit``.
        """
        scope_value = _normalize_scope(scope).value if scope is not None else None
        orms, total = await self.repo.list_for_org(
            org_id, scope=scope_value, subject_grn=subject_grn, limit=limit, offset=offset
        )
        entries = [orm_to_domain(orm) for orm in orms]
        if tag is not None:
            entries = [entry for entry in entries if tag in entry.tags]
        return entries, total

    async def update_entry(
        self,
        grn_str: str,
        *,
        updated_by: str,
        org_id: str | None = None,
        value: Any | None = None,
        tags: list[str] | None = None,
        expires_at: datetime | None = None,
        clear_expiry: bool = False,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> MemoryLayerEntry:
        """Update mutable fields; bumps the resource version."""
        orm = await self.repo.get_by_grn(grn_str, org_id=org_id)
        if value is not None:
            orm.value = value
        if tags is not None:
            orm.tags = tags
        if clear_expiry:
            orm.expires_at = None
        elif expires_at is not None:
            orm.expires_at = expires_at
        if metadata is not None:
            orm.resource_metadata = {**orm.resource_metadata, **metadata}
        orm.version += 1
        orm.updated_by = updated_by
        await self.event_repo.append(
            Event(
                type="resource_updated",
                principal_id=updated_by,
                organization_id=orm.org_id,
                resource_grn=grn_str,
                correlation_id=correlation_id,
                payload={"resource_type": "memory", "grn": grn_str, "key": orm.key},
                metadata={"service": "MemoryLayerService", "operation": "update_entry"},
            )
        )
        await self.session.commit()
        return orm_to_domain(orm)

    async def delete_entry(
        self,
        grn_str: str,
        *,
        deleted_by: str,
        org_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Hard-delete an entry; the audit event survives in the event store."""
        orm = await self.repo.get_by_grn(grn_str, org_id=org_id, include_expired=True)
        entry_org = orm.org_id
        entry_key = orm.key
        await self.repo.delete(orm)
        await self.event_repo.append(
            Event(
                type="resource_deleted",
                principal_id=deleted_by,
                organization_id=entry_org,
                resource_grn=grn_str,
                correlation_id=correlation_id,
                payload={"resource_type": "memory", "grn": grn_str, "key": entry_key},
                metadata={"service": "MemoryLayerService", "operation": "delete_entry"},
            )
        )
        await self.session.commit()
