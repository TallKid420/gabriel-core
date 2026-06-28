"""Events subsystem exceptions."""


class EventsError(Exception):
    """Base exception for Gabriel events subsystem."""
    pass


class HandlerNotFoundError(EventsError):
    """Raised when no handler is registered for a command type."""
    pass


class CommandValidationError(EventsError):
    """Raised when a command fails validation."""
    pass


class HandlerExecutionError(EventsError):
    """Raised when a handler fails during execution."""
    pass


class ProjectionError(EventsError):
    """Raised when a projection fails to update."""
    pass


class InvalidEventError(EventsError):
    """Raised when an event is malformed or invalid."""
    pass
