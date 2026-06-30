"""Policy evaluation engine: Determines if a request is allowed or denied."""
import fnmatch
from pydantic import BaseModel

from gabriel.policy.models import Policy, PolicyStatement, Effect


class EvaluationRequest(BaseModel):
    """A request to evaluate against policies.
    
    Represents a principal attempting an action on a resource.
    """
    
    principal: str
    """Principal GRN attempting the action (e.g., "principal:org:user/alice")."""
    
    action: str
    """Action being attempted (e.g., "identity:create_user", "resource:read")."""
    
    resource: str
    """Resource GRN being accessed (e.g., "grn:org:agent/123")."""


class PolicyEngine:
    """Evaluates requests against policies using "Default Deny" model.
    
    Evaluation rules:
    1. Default: DENY (nothing is allowed unless explicitly allowed)
    2. First matching ALLOW: Changes decision to ALLOW
    3. Any matching DENY: Immediately returns DENY (overrides all ALLOWs)
    
    This implements the principle of "Explicit Deny Wins" for security.
    """
    
    def __init__(self, policies: list[Policy] | None = None):
        """Initialize engine with policies.
        
        Args:
            policies: List of Policy resources. If None, defaults to empty (all denied).
        """
        self.policies = policies or []
    
    def evaluate(self, request: EvaluationRequest) -> Effect:
        """Evaluate a request against all policies.
        
        Args:
            request: The evaluation request.
            
        Returns:
            Effect: ALLOW or DENY.
            
        Process:
        - Start with DENY (default deny)
        - For each policy, for each statement:
          - If matches and DENY: return DENY immediately
          - If matches and ALLOW: set decision to ALLOW (but keep checking)
        - Return final decision
        """
        # Default: DENY (fail secure)
        decision = Effect.DENY
        
        for policy in self.policies:
            for statement in policy.statements:
                if self._matches(statement, request):
                    # Explicit DENY overrides everything
                    if statement.effect == Effect.DENY:
                        return Effect.DENY
                    
                    # ALLOW changes decision (but may be overridden by later DENY)
                    decision = Effect.ALLOW
        
        return decision
    
    def evaluate_batch(self, requests: list[EvaluationRequest]) -> list[Effect]:
        """Evaluate multiple requests.
        
        Args:
            requests: List of evaluation requests.
            
        Returns:
            list[Effect]: Decisions for each request.
        """
        return [self.evaluate(req) for req in requests]
    
    def _matches(self, statement: PolicyStatement, request: EvaluationRequest) -> bool:
        """Check if a statement matches a request using glob patterns.
        
        Uses fnmatch for glob-style pattern matching:
        - "*" matches everything
        - "*.txt" matches any .txt file
        - "grn:org:*/*:*" matches any resource in org
        
        Args:
            statement: The policy statement.
            request: The evaluation request.
            
        Returns:
            bool: True if all three patterns match.
        """
        p_match = fnmatch.fnmatch(request.principal, statement.principal_match)
        a_match = fnmatch.fnmatch(request.action, statement.action_match)
        r_match = fnmatch.fnmatch(request.resource, statement.resource_match)
        
        return p_match and a_match and r_match
    
    def add_policy(self, policy: Policy) -> None:
        """Add a policy to the engine.
        
        Args:
            policy: The policy to add.
        """
        self.policies.append(policy)
    
    def remove_policy(self, policy_grn: str) -> bool:
        """Remove a policy by GRN.
        
        Args:
            policy_grn: The GRN of the policy to remove.
            
        Returns:
            bool: True if policy was found and removed.
        """
        for i, policy in enumerate(self.policies):
            if str(policy.grn) == policy_grn:
                self.policies.pop(i)
                return True
        return False