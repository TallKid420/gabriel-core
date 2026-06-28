"""Policy models: Effect, PolicyStatement, and Policy resource."""
from enum import Enum
from typing import Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from gabriel.resource.models import Resource, ResourceState, ResourceType
from gabriel.resource.grn import GRN


class Effect(str, Enum):
    """Policy effect: ALLOW or DENY."""
    
    ALLOW = "allow"
    """Allow the action."""
    
    DENY = "deny"
    """Deny the action."""


class PolicyStatement(BaseModel):
    """A single statement within a policy.
    
    Statements use glob-style pattern matching:
    - "*" matches everything
    - "grn://org/*/resource" matches any resource type
    - "identity:*" matches any identity action
    """
    
    effect: Effect
    """What to do if this statement matches: ALLOW or DENY."""
    
    principal_match: str
    """Pattern to match against principal GRN (e.g., "grn://org/user/*", "*")."""
    
    action_match: str
    """Pattern to match against action (e.g., "identity:create_user", "*")."""
    
    resource_match: str
    """Pattern to match against resource GRN (e.g., "grn://org/agent/123", "*")."""
    
    condition: str | None = None
    """Optional condition for future expansion (e.g., time-based, IP-based)."""
    
    model_config = {"frozen": True}


class Policy(Resource):
    """A policy resource that defines what actions are allowed/denied.
    
    Policies follow the "Default Deny" and "Explicit Deny Wins" model:
    - Default: DENY (nothing is allowed unless explicitly allowed)
    - Explicit DENY in any policy overrides all ALLOWs
    
    Example:
        Policy with statements:
        1. ALLOW grn://org/user/* to call identity:* on grn://org/agent/*
        2. DENY bad_user to do anything
    """
    
    statements: list[PolicyStatement] = Field(default_factory=list)
    """List of policy statements (order matters; first match wins for ALLOW)."""
    
    model_config = {"frozen": True}
    
    @classmethod
    def create(
        cls,
        grn: GRN,
        org_id: str,
        created_by: str,
        statements: list[PolicyStatement],
        labels: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "Policy":
        """Create a new Policy resource.
        
        Args:
            grn: The policy GRN.
            org_id: Organization ID.
            created_by: Principal that created this policy.
            statements: List of policy statements.
            labels: Optional labels.
            metadata: Optional metadata.
            
        Returns:
            Policy: A new Policy resource.
        """
        return cls(
            grn=grn,
            org_id=org_id,
            resource_type=ResourceType.POLICY,
            state=ResourceState.ACTIVE,
            version=1,
            created_by=created_by,
            updated_by=created_by,
            statements=statements,
            labels=labels or {},
            metadata=metadata or {},
        )