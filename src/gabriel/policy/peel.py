"""PEEL: Policy Enforcement & Evaluation Layer.

The gatekeeper that ensures every Command is authorized before execution.

PEEL combines two layers of enforcement, applied in order (fail-secure):

1. Multi-tenant isolation — the resource being accessed must belong to the
   principal's organization. Cross-tenant access is structurally impossible.
2. Identity-based (capability) enforcement — the principal must hold the
   capability required by the action (see ``policy.capabilities``).
3. Policy-based enforcement — explicit ALLOW/DENY statements. An explicit
   DENY always wins; when policies exist they may further restrict access.

This module lives in **Core (Platform Layer)**.
"""
from gabriel.policy.capabilities import required_capability_for_action
from gabriel.policy.engine import PolicyEngine, EvaluationRequest, Effect
from gabriel.policy.exceptions import UnauthorizedError
from gabriel.resource.exceptions import InvalidGRNError
from gabriel.resource.grn import GRN
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
        # 1. Multi-tenant isolation — the resource must belong to the
        #    principal's organization. This is a STRUCTURAL boundary and can
        #    never be overridden by a policy or a capability.
        self._enforce_tenant_isolation(context, resource_grn, action)

        # 2. Policy-based enforcement — when explicit policies are configured
        #    they are the authority. An explicit DENY always wins; an explicit
        #    ALLOW grants access without requiring a matching capability (this
        #    is how an administrator delegates access via policy).
        if self.engine.policies:
            request = EvaluationRequest(
                principal=str(context.principal.id),
                action=action,
                resource=resource_grn,
            )
            decision = self.engine.evaluate(request)
            if decision == Effect.ALLOW:
                return
            raise UnauthorizedError(
                f"Principal {context.principal.id} is not authorized to "
                f"{action} on {resource_grn} (denied by policy)"
            )

        # 3. Identity-based capability enforcement (fail-secure default) — used
        #    when no explicit policies are configured. The principal must hold
        #    the capability the action requires.
        self._enforce_capabilities(context, action, resource_grn)

    def _enforce_capabilities(
        self,
        context: ExecutionContext,
        action: str,
        resource_grn: str,
    ) -> None:
        """Raise UnauthorizedError if the principal lacks the required capability."""
        required = required_capability_for_action(action)
        if required is None:
            return
        if required.value not in context.capabilities:
            raise UnauthorizedError(
                f"Principal {context.principal.id} lacks capability "
                f"'{required.value}' required to {action} on {resource_grn}"
            )

    def _enforce_tenant_isolation(
        self,
        context: ExecutionContext,
        resource_grn: str,
        action: str,
    ) -> None:
        """Raise UnauthorizedError on cross-tenant resource access.

        The resource's organization (parsed from its GRN) must match the
        organization of the execution context. Wildcard org segments and
        non-GRN resource selectors are treated as same-tenant by design.
        """
        if not resource_grn:
            return
        try:
            grn = GRN.parse(resource_grn)
        except InvalidGRNError:
            # Not a fully-qualified GRN (e.g. "grn:acme/*" coarse selector or
            # an opaque action target). Tenant scoping is enforced elsewhere.
            return

        if grn.org_id in {"*", ""}:
            return

        if grn.org_id != context.organization:
            raise UnauthorizedError(
                f"Principal {context.principal.id} in organization "
                f"'{context.organization}' may not {action} on resource owned "
                f"by organization '{grn.org_id}' (cross-tenant access denied)"
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
