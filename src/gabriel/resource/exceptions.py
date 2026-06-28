# TODO Add custom constructors only for exceptions where structured context is genuinely useful

class GabrielError(Exception):
    """Base exception for all Gabriel errors."""
    pass

class InvalidGRNError(GabrielError):
    """Raised when a GRN is malformed or cannot be parsed."""
    pass

class ResourceNotFoundError(GabrielError):
    """Raised when a resource cannot be located."""
    pass

class InvalidLifecycleTransitionError(GabrielError):
    """Raised when a lifecycle transition is not permitted."""
    pass

class ResourceTypeNotRegisteredError(GabrielError):
    """Raised when a resource type has not been registered."""
    pass

class DuplicateResourceTypeError(GabrielError):
    """Raised when a resource type is registered more than once."""
    pass