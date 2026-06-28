"""Gabriel policy layer: PEEL (Policy Enforcement & Evaluation Layer).

The gatekeeper that ensures every command is authorized before execution.

Implements:
- Policy resources (Effect, PolicyStatement, Policy)
- PolicyEngine (evaluates requests against policies)
- PEEL (enforces policies before command dispatch)
"""

from gabriel.policy.models import Effect, PolicyStatement, Policy
from gabriel.policy.engine import PolicyEngine, EvaluationRequest
from gabriel.policy.peel import PEEL
from gabriel.policy.exceptions import (
    PolicyError,
    UnauthorizedError,
    PolicyEvaluationError,
)

__all__ = [
    # Models
    "Effect",
    "PolicyStatement",
    "Policy",
    # Engine
    "PolicyEngine",
    "EvaluationRequest",
    # PEEL
    "PEEL",
    # Exceptions
    "PolicyError",
    "UnauthorizedError",
    "PolicyEvaluationError",
]
