"""Gabriel runtime: Execution context and lifecycle management.

The runtime subsystem implements the execution pipeline:

    command → dispatcher → event → ExecutionContext → Execution → Scheduler

ExecutionContext is the immutable "process block" that determines what
a principal can do. Execution tracks the mutable state of a running context.
"""

from gabriel.runtime.context import ExecutionContext
from gabriel.runtime.capabilities import Capability
from gabriel.runtime.execution import (
    ExecutionState,
    ExecutionContextBuilder,
    Execution,
)
from gabriel.runtime.scheduler import Scheduler
from gabriel.runtime.scope import ScopedClient
from gabriel.runtime.exceptions import (
    RuntimeError,
    ExecutionContextError,
    CapabilityError,
    ExecutionError,
    SchedulerError,
    InvalidExecutionStateError,
)

__all__ = [
    # Context
    "ExecutionContext",
    # Capabilities
    "Capability",
    # Execution lifecycle
    "ExecutionState",
    "ExecutionContextBuilder",
    "Execution",
    # Scheduling
    "Scheduler",
    # Scoped access
    "ScopedClient",
    # Exceptions
    "RuntimeError",
    "ExecutionContextError",
    "CapabilityError",
    "ExecutionError",
    "SchedulerError",
    "InvalidExecutionStateError",
]
