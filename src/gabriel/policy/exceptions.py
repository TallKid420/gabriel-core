"""Policy exceptions."""


class PolicyError(Exception):
    """Base exception for policy-related errors."""
    pass


class UnauthorizedError(PolicyError):
    """Raised when a principal is not authorized to perform an action.
    
    This is the result of PEEL evaluation returning DENY.
    """
    pass


class PolicyEvaluationError(PolicyError):
    """Raised when policy evaluation itself fails (not authorization failure)."""
    pass
