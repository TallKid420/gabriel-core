"""SQLAlchemy-backed EventStore adapter for gateway persistence.

This keeps the EventStore interface used by Dispatcher while persisting events
to the ADR-017 transactional outbox table.
"""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gabriel.events.event import Event
from gabriel.events.orm import EventORM
from gabriel.events.repository import EventRepository


def _orm_to_event(orm: EventORM) -> Event:
    return Event(
        id=orm.id,
        type=orm.type,
        occurred_at=orm.occurred_at,
        principal_id=orm.principal_id,
        organization_id=orm.organization_id,
        resource_grn=orm.resource_grn,
        correlation_id=orm.correlation_id,
        causation_id=orm.causation_id,
        payload=orm.payload or {},
        metadata=orm.event_metadata or {},
    )


class SqlAlchemyEventStore:
    """EventStore implementation backed by SQLAlchemy + events table.

    Writes are committed transactionally via EventRepository; reads are served
    from an in-memory mirror that is hydrated from the database at startup and
    updated on each append.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        initial_events: Sequence[Event] | None = None,
    ):
        self._session_factory = session_factory
        self._events: list[Event] = list(initial_events or [])

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Session factory backing this store (primary DB or fallback)."""
        return self._session_factory

    @classmethod
    async def load_from_db(
        cls,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> "SqlAlchemyEventStore":
        async with session_factory() as session:
            result = await session.execute(
                select(EventORM).order_by(EventORM.occurred_at, EventORM.id)
            )
            rows = list(result.scalars().all())
        return cls(session_factory=session_factory, initial_events=[_orm_to_event(row) for row in rows])

    async def append(self, event: Event) -> None:
        await self.append_many([event])

    async def append_many(self, events: list[Event]) -> None:
        if not events:
            return

        async with self._session_factory() as session:
            repo = EventRepository(session)
            await repo.append_many(events)
            await session.commit()

        self._events.extend(events)

    def events(self) -> list[Event]:
        return list(self._events)

    def events_for_organization(self, organization_id: str) -> list[Event]:
        return [event for event in self._events if event.organization_id == organization_id]

    def events_for_resource(self, resource_grn: str) -> list[Event]:
        return [event for event in self._events if event.resource_grn == resource_grn]

    def events_by_type(self, event_type: str) -> list[Event]:
        return [event for event in self._events if event.type == event_type]

    def events_for_principal(self, principal_id: str) -> list[Event]:
        return [event for event in self._events if event.principal_id == principal_id]

    def events_by_correlation_id(self, correlation_id: str) -> list[Event]:
        return [event for event in self._events if event.correlation_id == correlation_id]

    def count(self) -> int:
        return len(self._events)

    def clear(self) -> None:
        self._events.clear()