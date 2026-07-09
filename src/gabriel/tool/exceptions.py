class ToolInvocationError(Exception):
    """Raised when a tool invocation fails for any reason."""


class SchemaValidationError(ToolInvocationError):
    """Raised when input or output fails JSON Schema validation."""


class ToolNotFoundError(ToolInvocationError):
    """Raised when the tool GRN cannot be resolved or the callable is missing."""


class ConfirmationRequiredError(ToolInvocationError):
    """Raised when a REQUIRES_CONFIRMATION tool is dispatched without the
    ``confirmed=True`` flag.  The caller must surface the pending invocation to
    the user and re-invoke with confirmation.
    """
