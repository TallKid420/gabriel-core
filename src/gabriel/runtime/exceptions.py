"""Runtime subsystem exceptions."""


class RuntimeError(Exception):
    """Base exception for Gabriel runtime."""
    pass


class ExecutionContextError(RuntimeError):
    """Raised when execution context is invalid."""
    pass


class CapabilityError(RuntimeError):
    """Raised when a capability is missing or invalid."""
    pass


class ExecutionError(RuntimeError):
    """Raised during execution failures."""
    pass


class SchedulerError(RuntimeError):
    """Raised when scheduler operations fail."""
    pass


class RuntimeNotFoundError(RuntimeError):
    """Raised when Runtime cannot be found"""
    pass


class InvalidExecutionStateError(ExecutionError):
    """Raised when execution state transition is invalid."""
    pass