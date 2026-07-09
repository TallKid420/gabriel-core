"""Scoped memory client with PEEL authorisation (ADR-019, Task 3.3).

ScopedMemoryClient is the single entry point agents use to interact with
memory. It enforces two responsibilities before any backend call:

1. **Tenant isolation** — the client is bound to an ExecutionContext; any
   attempt to read or write memory belonging to a different org is denied
   structurally (the org_id is baked into every backend call).

2. **PEEL authorisation** — if a PolicyEngine is supplied, every operation
   is evaluated: action ``memory:write``, ``memory:read``, ``memory:search``,
   or ``memory:forget`` against the principal and org resource GRN. Denied
   operations raise ``PermissionError`` and emit a ``memory_access_denied``
   audit event.

Porting note: PEEL evaluation reuses the existing PolicyEngine + Effect
model from gabriel.policy, matching the Dispatcher integration pattern.
"""
from __future__ import annotations

from typing import Any, List, Optional

from gabriel.memory.contract import MemoryAccessInterface
from gabriel.memory.models import MemoryEntry, MemoryLayer
from gabriel.runtime.context import ExecutionContext


class ScopedMemoryClient:
    """Layer-aware memory client bound to an ExecutionContext.

    Parameters
    ----------
    context:
        The current execution context (principal + org). Used for tenant
        isolation and PEEL evaluation.
    provider:
        A MemoryAccessInterface backend (LocalMemoryProvider,
        PostgresMemoryBackend, …).
    policy_engine:
        Optional PolicyEngine. When provided, every memory operation is
        evaluated before the backend is called. Pass ``None`` in tests or
        during bootstrapping before policies are loaded.
    dispatcher:
        Optional Dispatcher used to emit audit events on PEEL decisions.
        If absent, denials are logged but no event is persisted.
    """

    def __init__(
        self,
        context: ExecutionContext,
        provider: MemoryAccessInterface,
        policy_engine: Any | None = None,
        dispatcher: Any | None = None,
    ) -> None:
        self.context = context
        self.provider = provider
        self._policy_engine = policy_engine
        self._dispatcher = dispatcher

    # ------------------------------------------------------------------
    # Internal PEEL gate
    # ------------------------------------------------------------------

    def _check_peel(self, action: str) -> None:
        """Evaluate a memory action through PEEL; raise on denial.

        The resource GRN for memory operations is the org-level memory
        namespace: ``grn:{org_id}:memory/*``.

        Emits a ``memory_access_denied`` audit event on denial so that
        cross-org access attempts are recorded (ADR-019).

        Raises:
            PermissionError: If PEEL denies the action.
        """
        if self._policy_engine is None:
            return  # No engine wired — open in dev mode

        from gabriel.policy.engine import EvaluationRequest
        from gabriel.policy.models import Effect

        principal_str = str(self.context.principal.id)
        resource_grn = f"grn:{self.context.organization}:memory/*"

        req = EvaluationRequest(
            principal=principal_str,
            action=action,
            resource=resource_grn,
        )
        decision = self._policy_engine.evaluate(req)

        if decision == Effect.DENY:
            self._emit_audit_event(action=action, decision="DENY")
            raise PermissionError(
                f"PEEL denied '{action}' for principal '{principal_str}' "
                f"on '{resource_grn}'"
            )

        self._emit_audit_event(action=action, decision="ALLOW")

    def _emit_audit_event(self, *, action: str, decision: str) -> None:
        """Emit a memory audit event through the dispatcher if available.

        Non-blocking — failures are swallowed so a telemetry issue never
        interrupts the agent's execution path.
        """
        if self._dispatcher is None:
            return
        try:
            import asyncio
            from gabriel.events.event import Event
            from uuid_extensions import uuid7

            event = Event(
                id=str(uuid7()),
                type="memory_access_audited",
                organization_id=self.context.organization,
                principal_id=str(self.context.principal.id),
                correlation_id=str(self.context.correlation_id),
                payload={
                    "action": action,
                    "decision": decision,
                    "org_id": self.context.organization,
                },
            )
            # publish() is telemetry-only (Track 2) — safe to fire-and-forget
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._dispatcher.publish(event))
        except Exception:
            pass  # Audit failure must never block the operation

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def write(
        self, content: Any, layer: MemoryLayer = MemoryLayer.SHORT_TERM
    ) -> str:
        """Store content in the specified memory layer.

        PEEL action: ``memory:write``
        """
        self._check_peel("memory:write")

        entry = MemoryEntry(
            content=content,
            layer=layer,
            metadata={
                "principal": str(self.context.principal.id),
                "org": self.context.organization,
            },
        )
        return await self.provider.store(entry)

    async def read(
        self,
        layer: MemoryLayer = MemoryLayer.SHORT_TERM,
        query: str | None = None,
        limit: int = 10,
    ) -> List[MemoryEntry]:
        """Retrieve entries from a layer with optional keyword filter.

        PEEL action: ``memory:read``
        """
        self._check_peel("memory:read")
        return await self.provider.retrieve(layer=layer, query=query, limit=limit)

    async def search(
        self,
        query: str,
        layer: Optional[MemoryLayer] = None,
        limit: int = 10,
    ) -> List[MemoryEntry]:
        """Semantic search across memory entries ranked by relevance.

        PEEL action: ``memory:search``

        Example::

            results = await client.search("What did we discuss about X?")
        """
        self._check_peel("memory:search")
        return await self.provider.search(query=query, layer=layer, limit=limit)

    async def forget(self, memory_id: str) -> None:
        """Hard-delete a memory entry by ID.

        PEEL action: ``memory:forget``
        """
        self._check_peel("memory:forget")
        await self.provider.forget(memory_id)
