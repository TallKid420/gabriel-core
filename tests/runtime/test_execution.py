"""Tests for Execution and ExecutionState."""
import pytest
from datetime import datetime, timezone

from gabriel.runtime.execution import (
    ExecutionState,
    ExecutionContextBuilder,
    Execution,
    utcnow,
)
from gabriel.runtime.exceptions import InvalidExecutionStateError


class TestExecutionState:
    """Test ExecutionState enum."""

    def test_execution_states_exist(self):
        """All expected states exist."""
        assert ExecutionState.PENDING
        assert ExecutionState.RUNNING
        assert ExecutionState.WAITING
        assert ExecutionState.COMPLETED
        assert ExecutionState.FAILED
        assert ExecutionState.CANCELLED

    def test_execution_states_are_strings(self):
        """ExecutionState values are strings."""
        assert isinstance(ExecutionState.PENDING.value, str)
        assert ExecutionState.PENDING.value == "pending"

    def test_all_states_are_comparable(self):
        """ExecutionStates can be compared."""
        assert ExecutionState.PENDING != ExecutionState.RUNNING
        assert ExecutionState.PENDING == ExecutionState.PENDING


class TestExecutionTransitions:
    """Test state transitions."""

    def test_pending_to_running(self, execution: Execution):
        """PENDING → RUNNING is valid."""
        assert execution.state == ExecutionState.PENDING
        execution.transition_to(ExecutionState.RUNNING)
        assert execution.state == ExecutionState.RUNNING

    def test_pending_to_cancelled(self, execution: Execution):
        """PENDING → CANCELLED is valid."""
        execution.transition_to(ExecutionState.CANCELLED)
        assert execution.state == ExecutionState.CANCELLED

    def test_running_to_completed(self, execution: Execution):
        """RUNNING → COMPLETED is valid."""
        execution.transition_to(ExecutionState.RUNNING)
        execution.transition_to(ExecutionState.COMPLETED)
        assert execution.state == ExecutionState.COMPLETED
        assert execution.completed_at is not None

    def test_running_to_failed(self, execution: Execution):
        """RUNNING → FAILED is valid."""
        execution.transition_to(ExecutionState.RUNNING)
        execution.transition_to(ExecutionState.FAILED)
        assert execution.state == ExecutionState.FAILED
        assert execution.completed_at is not None

    def test_running_to_waiting(self, execution: Execution):
        """RUNNING → WAITING is valid."""
        execution.transition_to(ExecutionState.RUNNING)
        execution.transition_to(ExecutionState.WAITING)
        assert execution.state == ExecutionState.WAITING

    def test_waiting_to_running(self, execution: Execution):
        """WAITING → RUNNING is valid."""
        execution.transition_to(ExecutionState.RUNNING)
        execution.transition_to(ExecutionState.WAITING)
        execution.transition_to(ExecutionState.RUNNING)
        assert execution.state == ExecutionState.RUNNING

    def test_invalid_pending_to_completed(self, execution: Execution):
        """PENDING → COMPLETED is invalid."""
        with pytest.raises(InvalidExecutionStateError):
            execution.transition_to(ExecutionState.COMPLETED)

    def test_invalid_completed_transition(self, execution: Execution):
        """COMPLETED is terminal, no transitions allowed."""
        execution.transition_to(ExecutionState.RUNNING)
        execution.transition_to(ExecutionState.COMPLETED)
        with pytest.raises(InvalidExecutionStateError):
            execution.transition_to(ExecutionState.RUNNING)

    def test_invalid_failed_transition(self, execution: Execution):
        """FAILED is terminal, no transitions allowed."""
        execution.transition_to(ExecutionState.RUNNING)
        execution.transition_to(ExecutionState.FAILED)
        with pytest.raises(InvalidExecutionStateError):
            execution.transition_to(ExecutionState.COMPLETED)

    def test_invalid_cancelled_transition(self, execution: Execution):
        """CANCELLED is terminal, no transitions allowed."""
        execution.transition_to(ExecutionState.CANCELLED)
        with pytest.raises(InvalidExecutionStateError):
            execution.transition_to(ExecutionState.RUNNING)


class TestExecutionTerminal:
    """Test terminal state detection."""

    def test_is_terminal_completed(self, execution: Execution):
        """COMPLETED is terminal."""
        execution.transition_to(ExecutionState.RUNNING)
        execution.transition_to(ExecutionState.COMPLETED)
        assert execution.is_terminal()

    def test_is_terminal_failed(self, execution: Execution):
        """FAILED is terminal."""
        execution.transition_to(ExecutionState.RUNNING)
        execution.transition_to(ExecutionState.FAILED)
        assert execution.is_terminal()

    def test_is_terminal_cancelled(self, execution: Execution):
        """CANCELLED is terminal."""
        execution.transition_to(ExecutionState.CANCELLED)
        assert execution.is_terminal()

    def test_not_terminal_pending(self, execution: Execution):
        """PENDING is not terminal."""
        assert not execution.is_terminal()

    def test_not_terminal_running(self, execution: Execution):
        """RUNNING is not terminal."""
        execution.transition_to(ExecutionState.RUNNING)
        assert not execution.is_terminal()

    def test_not_terminal_waiting(self, execution: Execution):
        """WAITING is not terminal."""
        execution.transition_to(ExecutionState.RUNNING)
        execution.transition_to(ExecutionState.WAITING)
        assert not execution.is_terminal()


class TestExecutionDuration:
    """Test duration calculation."""

    def test_duration_not_set_on_pending(self, execution: Execution):
        """PENDING execution has no completed_at."""
        assert execution.completed_at is None

    def test_duration_set_on_completion(self, execution: Execution):
        """Completed execution has completed_at set."""
        execution.transition_to(ExecutionState.RUNNING)
        execution.transition_to(ExecutionState.COMPLETED)
        assert execution.completed_at is not None

    def test_duration_seconds_pending(self, execution: Execution):
        """duration_seconds returns current duration for pending."""
        duration = execution.duration_seconds()
        assert duration >= 0

    def test_duration_seconds_completed(self, execution: Execution):
        """duration_seconds returns elapsed time after completion."""
        execution.transition_to(ExecutionState.RUNNING)
        execution.transition_to(ExecutionState.COMPLETED)
        duration = execution.duration_seconds()
        assert duration >= 0


class TestExecutionContextBuilder:
    """Test ExecutionContextBuilder."""

    def test_builder_from_event(
        self, context_builder: ExecutionContextBuilder, test_event, principal
    ):
        """Builder creates context from event."""
        ctx = context_builder.from_event(test_event, principal)
        assert ctx.execution_id is not None
        assert ctx.principal == principal
        assert ctx.organization == test_event.organization_id
        # correlation_id comes from event.correlation_id (string) converted to UUID
        assert str(ctx.correlation_id) == test_event.correlation_id
        assert str(ctx.causation_id) == test_event.id

    def test_builder_generates_unique_execution_ids(
        self, context_builder: ExecutionContextBuilder, test_event, principal
    ):
        """Builder generates unique execution IDs for multiple calls."""
        ctx1 = context_builder.from_event(test_event, principal)
        ctx2 = context_builder.from_event(test_event, principal)
        assert ctx1.execution_id != ctx2.execution_id

    def test_builder_preserves_organization(
        self, context_builder: ExecutionContextBuilder, test_event, principal
    ):
        """Builder preserves organization from event."""
        ctx = context_builder.from_event(test_event, principal)
        assert ctx.organization == principal.id.org_id

    def test_builder_creates_metadata(
        self, context_builder: ExecutionContextBuilder, test_event, principal
    ):
        """Builder includes event info in metadata."""
        ctx = context_builder.from_event(test_event, principal)
        assert "event_id" in ctx.metadata
        assert "event_type" in ctx.metadata


class TestExecution:
    """Test Execution class."""

    def test_execution_created_in_pending_state(self, execution: Execution):
        """Execution starts in PENDING."""
        assert execution.state == ExecutionState.PENDING

    def test_execution_has_context(self, execution: Execution):
        """Execution has execution context."""
        assert execution.context is not None

    def test_execution_tracks_start_time(self, execution: Execution):
        """Execution tracks when it started."""
        assert execution.started_at is not None

    def test_execution_no_error_initially(self, execution: Execution):
        """New execution has no error."""
        assert execution.error is None

    def test_execution_no_result_initially(self, execution: Execution):
        """New execution has no result."""
        assert execution.result is None

    def test_execution_with_result(self, execution: Execution):
        """Execution can have result set."""
        result = {"status": "success", "value": 42}
        execution.result = result
        assert execution.result == result

    def test_execution_with_error(self, execution: Execution):
        """Execution can have error set."""
        execution.error = "Something went wrong"
        assert execution.error == "Something went wrong"
