from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, JSON, String, and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from gabriel.database.base import Base
from gabriel.events.audit import AuditEvent, PeelEvaluationEvent, PolicyChangeEvent
from gabriel.events.event import Event
from gabriel.events.projection import Projection


class AuditLogORM(Base):
    """Read model table for auditable events."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    principal_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    action: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resource_grn: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    event_metadata: Mapped[dict[str, Any]] = mapped_column("meta", JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_audit_log_time_principal_decision", "occurred_at", "principal_id", "decision"),
    )


class AuditProjection(Projection):
    """Projection that persists audit events and supports filtered queries."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    @property
    def event_types(self) -> list[str]:
        return ["peel_evaluation", "policy_changed"]

    async def handle_event(self, event: Event) -> None:
        if event.type not in self.event_types:
            return

        row = AuditLogORM(
            id=event.id,
            event_type=event.type,
            occurred_at=event.occurred_at,
            organization_id=event.organization_id,
            principal_id=event.principal_id,
            decision=(event.payload or {}).get("decision"),
            action=(event.payload or {}).get("action"),
            resource_grn=event.resource_grn,
            correlation_id=event.correlation_id,
            payload=dict(event.payload or {}),
            event_metadata=dict(event.metadata or {}),
        )

        async with self._session_factory() as session:
            existing = await session.get(AuditLogORM, event.id)
            if existing is None:
                session.add(row)
            else:
                existing.event_type = row.event_type
                existing.occurred_at = row.occurred_at
                existing.organization_id = row.organization_id
                existing.principal_id = row.principal_id
                existing.decision = row.decision
                existing.action = row.action
                existing.resource_grn = row.resource_grn
                existing.correlation_id = row.correlation_id
                existing.payload = row.payload
                existing.event_metadata = row.event_metadata
            await session.commit()

    async def reset(self) -> None:
        async with self._session_factory() as session:
            await session.execute(delete(AuditLogORM))
            await session.commit()

    async def query(
        self,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        principal_id: str | None = None,
        decision: str | None = None,
        organization_id: str | None = None,
        limit: int = 200,
    ) -> list[AuditEvent]:
        clauses = []
        if start_time is not None:
            clauses.append(AuditLogORM.occurred_at >= start_time)
        if end_time is not None:
            clauses.append(AuditLogORM.occurred_at <= end_time)
        if principal_id is not None:
            clauses.append(AuditLogORM.principal_id == principal_id)
        if decision is not None:
            clauses.append(AuditLogORM.decision == decision)
        if organization_id is not None:
            clauses.append(AuditLogORM.organization_id == organization_id)

        stmt = select(AuditLogORM)
        if clauses:
            stmt = stmt.where(and_(*clauses))
        stmt = stmt.order_by(AuditLogORM.occurred_at.desc()).limit(limit)

        async with self._session_factory() as session:
            result = await session.execute(stmt)
            rows = result.scalars().all()

        return [_row_to_event(row) for row in rows]


def _row_to_event(row: AuditLogORM) -> AuditEvent:
    kwargs = {
        "id": row.id,
        "type": row.event_type,
        "occurred_at": row.occurred_at,
        "principal_id": row.principal_id,
        "organization_id": row.organization_id,
        "resource_grn": row.resource_grn,
        "correlation_id": row.correlation_id,
        "payload": dict(row.payload or {}),
        "metadata": dict(row.event_metadata or {}),
    }
    if row.event_type == "peel_evaluation":
        return PeelEvaluationEvent(**kwargs)
    if row.event_type == "policy_changed":
        return PolicyChangeEvent(**kwargs)
    return AuditEvent(**kwargs)


__all__ = ["AuditLogORM", "AuditProjection"]
