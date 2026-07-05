"""Resource projection: builds materialized resource read model from events."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gabriel.events.event import Event
from gabriel.events.projection import Projection
from gabriel.resource.read_model_orm import ResourceProjectionORM


class ResourceReadModelProjection(Projection):
    """Persist and cache latest resource state for fast reads/lists."""

    _CREATE_EVENTS = {"resource_created", "agent_created"}
    _UPDATE_EVENTS = {"resource_updated", "agent_enabled", "agent_disabled"}
    _DELETE_EVENTS = {"resource_deleted", "agent_deleted"}

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory
        self._resources: dict[str, dict[str, Any]] = {}

    @property
    def event_types(self) -> list[str]:
        return sorted(self._CREATE_EVENTS | self._UPDATE_EVENTS | self._DELETE_EVENTS)

    async def bootstrap(self) -> None:
        """Load current projection rows into memory on startup."""
        async with self._session_factory() as session:
            result = await session.execute(select(ResourceProjectionORM))
            rows = result.scalars().all()

        self._resources = {row.grn: _row_to_resource_dict(row) for row in rows}

    async def is_empty(self) -> bool:
        if self._resources:
            return False

        async with self._session_factory() as session:
            result = await session.execute(select(ResourceProjectionORM.grn).limit(1))
            return result.scalar_one_or_none() is None

    async def handle_event(self, event: Event) -> None:
        grn = event.resource_grn
        if not grn:
            return

        previous = self._resources.get(grn, {"grn": grn, "attributes": {}, "payload": {}})
        next_state = _apply_event(previous, event)
        self._resources[grn] = next_state
        await self._upsert(next_state, event)

    async def reset(self) -> None:
        async with self._session_factory() as session:
            await session.execute(delete(ResourceProjectionORM))
            await session.commit()
        self._resources.clear()

    def get_resource(self, grn: str) -> dict[str, Any] | None:
        resource = self._resources.get(grn)
        if not resource or resource.get("state") == "deleted":
            return None
        return dict(resource)

    def list_resources(
        self,
        organization_id: str,
        resource_type: str | None = None,
        include_deleted: bool = False,
    ) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        for resource in self._resources.values():
            if resource.get("organization_id") != organization_id:
                continue
            if resource_type and resource.get("resource_type") != resource_type:
                continue
            if not include_deleted and resource.get("state") == "deleted":
                continue
            resources.append(dict(resource))
        return resources

    async def _upsert(self, resource: dict[str, Any], event: Event) -> None:
        async with self._session_factory() as session:
            row = await session.get(ResourceProjectionORM, resource["grn"])
            if row is None:
                row = ResourceProjectionORM(grn=resource["grn"], organization_id=event.organization_id)
                session.add(row)

            row.organization_id = event.organization_id
            row.resource_type = resource.get("resource_type")
            row.state = str(resource.get("state") or "active")
            row.attributes = dict(resource.get("attributes") or {})
            row.payload = _extract_payload(resource)
            row.last_event_type = event.type
            row.last_event_at = event.occurred_at
            row.updated_at = event.occurred_at
            await session.commit()


def _apply_event(current: dict[str, Any], event: Event) -> dict[str, Any]:
    next_state = dict(current)
    payload = dict(event.payload or {})

    next_state.setdefault("grn", event.resource_grn)
    next_state["organization_id"] = event.organization_id

    if event.type in ResourceReadModelProjection._CREATE_EVENTS:
        next_state.update(payload)
        next_state["state"] = "active"
    elif event.type in ResourceReadModelProjection._UPDATE_EVENTS:
        next_state.update(payload)
    elif event.type in ResourceReadModelProjection._DELETE_EVENTS:
        next_state["state"] = "deleted"

    if "resource_type" not in next_state or next_state["resource_type"] is None:
        next_state["resource_type"] = payload.get("resource_type")

    if "attributes" not in next_state or not isinstance(next_state["attributes"], dict):
        next_state["attributes"] = {}

    return next_state


def _extract_payload(resource: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in resource.items()
        if key not in {"grn", "organization_id", "last_event_type", "last_event_at"}
    }


def _row_to_resource_dict(row: ResourceProjectionORM) -> dict[str, Any]:
    base = dict(row.payload or {})
    base["grn"] = row.grn
    base["organization_id"] = row.organization_id
    base["resource_type"] = row.resource_type
    base["state"] = row.state
    base["attributes"] = dict(row.attributes or {})
    return base