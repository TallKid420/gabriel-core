"""Execution state and lifecycle management."""
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID
from typing import Any

from gabriel.events.event import Event
from gabriel.runtime.context import ExecutionContext
from gabriel.runtime.exceptions import InvalidExecutionStateError


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExecutionState(str, Enum):
    """Lifecycle state of an execution.
    
    PENDING → RUNNING → COMPLETED (or FAILED, CANCELLED, WAITING)
    """

    PENDING = "pending"
    """Execution scheduled but not started."""

    RUNNING = "running"
    """Execution is currently executing."""

    WAITING = "waiting"
    """Execution is waiting (e.g., for I/O, another execution)."""

    COMPLETED = "completed"
    """Execution completed successfully."""

    FAILED = "failed"
    """Execution failed with an error."""

    CANCELLED = "cancelled"
    """Execution was cancelled."""


class ExecutionContextBuilder:
    """Builder for ExecutionContext from events."""

    def from_event(
        self,
        event: Event,
        principal,
    ) -> ExecutionContext:
        """Build an ExecutionContext from an event and principal.
        
        Args:
            event: The event that triggered the execution.
            principal: The principal executing.
            
        Returns:
            ExecutionContext: The built context.
        """
        import uuid

        # Extract or generate IDs
        execution_id = uuid.uuid4()
        correlation_id = (
            UUID(event.correlation_id)
            if event.correlation_id
            else execution_id
        )

        return ExecutionContext(
            execution_id=execution_id,
            principal=principal,
            organization=event.organization_id,
            correlation_id=correlation_id,
            causation_id=UUID(event.id) if event.id else None,
            session_id=None,
            resource=event.resource_grn,
            started_at=utcnow(),
            capabilities=frozenset(
                [cap.value for cap in principal.capabilities]
                if hasattr(principal, "capabilities")
                else []
            ),
            metadata={
                "event_id": event.id,
                "event_type": event.type,
            },
        )


@dataclass
class Execution:
    """An execution: context + state + result."""

    context: ExecutionContext
    """Immutable execution context."""

    state: ExecutionState = ExecutionState.PENDING
    """Current execution state."""

    started_at: datetime = field(default_factory=utcnow)
    """When execution started."""

    completed_at: datetime | None = None
    """When execution completed (or failed/cancelled)."""

    error: str | None = None
    """Error message if execution failed."""

    result: Any = None
    """Execution result (if completed)."""

    def transition_to(self, new_state: ExecutionState) -> None:
        """Transition to a new state.
        
        Args:
            new_state: The target state.
            
        Raises:
            InvalidExecutionStateError: If transition is invalid.
        """
        valid_transitions = {
            ExecutionState.PENDING: {ExecutionState.RUNNING, ExecutionState.CANCELLED},
            ExecutionState.RUNNING: {
                ExecutionState.COMPLETED,
                ExecutionState.FAILED,
                ExecutionState.CANCELLED,
                ExecutionState.WAITING,
            },
            ExecutionState.WAITING: {
                ExecutionState.RUNNING,
                ExecutionState.CANCELLED,
                ExecutionState.FAILED,
            },
            ExecutionState.COMPLETED: set(),  # Terminal
            ExecutionState.FAILED: set(),  # Terminal
            ExecutionState.CANCELLED: set(),  # Terminal
        }

        if new_state not in valid_transitions.get(self.state, set()):
            raise InvalidExecutionStateError(
                f"Invalid transition from {self.state} to {new_state}"
            )

        self.state = new_state
        if new_state in {
            ExecutionState.COMPLETED,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
        }:
            self.completed_at = utcnow()

    def is_terminal(self) -> bool:
        """Check if execution is in a terminal state."""
        return self.state in {
            ExecutionState.COMPLETED,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
        }

    def duration_seconds(self) -> float | None:
        """Get execution duration in seconds.
        
        Returns:
            float | None: Duration in seconds, or None if not completed.
        """
        end = self.completed_at or utcnow()
        return (end - self.started_at).total_seconds()