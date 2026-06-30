"""PEEL: Policy Enforcement & Evaluation Layer.

The gatekeeper that ensures every Command is authorized before execution.
"""
from gabriel.policy.engine import PolicyEngine, EvaluationRequest, Effect
from gabriel.policy.exceptions import UnauthorizedError
from gabriel.runtime.context import ExecutionContext


class PEEL:
    """Policy Enforcement & Evaluation Layer.
    
    PEEL intercepts every command and evaluates it against policies before
    allowing execution. It is the "gatekeeper" that makes Gabriel secure.
    
    Responsibilities:
    - Receive authorization requests
    - Evaluate against policies via PolicyEngine
    - Either allow or deny based on policies
    - Raise UnauthorizedError for denials
    """
    
    def __init__(self, engine: PolicyEngine):
        """Initialize PEEL with a policy engine.
        
        Args:
            engine: The PolicyEngine that will evaluate requests.
        """
        self.engine = engine
    
    async def authorize(
        self,
        context: ExecutionContext,
        action: str,
        resource_grn: str,
    ) -> None:
        """Authorize an action within an execution context.
        
        This method is called before every command execution.
        
        Args:
            context: The execution context.
            action: The action being attempted (e.g., "identity:create_user").
            resource_grn: The resource GRN being accessed.
            
        Raises:
            UnauthorizedError: If the action is denied by policy.
            
        Example:
            await peel.authorize(context, "organization:create", "grn:org:org/*")
        """
        # Build evaluation request
        request = EvaluationRequest(
            principal=str(context.principal.id),
            action=action,
            resource=resource_grn,
        )
        
        # Evaluate against policies
        decision = self.engine.evaluate(request)
        
        # If denied, raise UnauthorizedError
        if decision == Effect.DENY:
            raise UnauthorizedError(
                f"Principal {context.principal.id} is not authorized to "
                f"{action} on {resource_grn}"
            )
    
    async def authorize_batch(
        self,
        context: ExecutionContext,
        requests: list[tuple[str, str]],
    ) -> None:
        """Authorize multiple actions within same context.
        
        Args:
            context: The execution context.
            requests: List of (action, resource_grn) tuples.
            
        Raises:
            UnauthorizedError: On first denied action.
        """
        for action, resource_grn in requests:
            await self.authorize(context, action, resource_grn)
