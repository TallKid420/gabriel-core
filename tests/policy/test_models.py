"""Tests for policy models: Effect, PolicyStatement, Policy."""
import pytest
from pydantic import ValidationError

from gabriel.policy.models import Effect, PolicyStatement, Policy, ResourceType
from gabriel.resource.grn import GRN


class TestEffect:
    """Test Effect enum."""

    def test_effect_allow(self):
        """ALLOW effect has correct value."""
        assert Effect.ALLOW.value == "allow"

    def test_effect_deny(self):
        """DENY effect has correct value."""
        assert Effect.DENY.value == "deny"


class TestPolicyStatement:
    """Test PolicyStatement model."""

    def test_statement_creation(self):
        """Create a policy statement."""
        stmt = PolicyStatement(
            effect=Effect.ALLOW,
            principal_match="*",
            action_match="read",
            resource_match="grn:org:doc/*:*",
        )
        assert stmt.effect == Effect.ALLOW
        assert stmt.principal_match == "*"

    def test_statement_with_condition(self):
        """Create statement with condition."""
        stmt = PolicyStatement(
            effect=Effect.DENY,
            principal_match="contractor:*",
            action_match="admin:*",
            resource_match="*",
            condition="time_of_day == 'business_hours'",
        )
        assert stmt.condition is not None

    def test_statement_immutable(self):
        """Policy statements are frozen."""
        stmt = PolicyStatement(
            effect=Effect.ALLOW,
            principal_match="*",
            action_match="*",
            resource_match="*",
        )
        with pytest.raises(ValidationError):
            stmt.effect = Effect.DENY


class TestPolicy:
    """Test Policy resource model."""

    def test_policy_creation_with_create(self, org_id: str):
        """Create policy using create() factory."""
        grn = GRN(
            org_id=org_id,
            resource_type=ResourceType.POLICY,
            resource_id="allow-read",
        )
        stmt = PolicyStatement(
            effect=Effect.ALLOW,
            principal_match="*",
            action_match="read",
            resource_match="*",
        )
        policy = Policy.create(
            grn=grn,
            org_id=org_id,
            created_by="admin",
            statements=[stmt],
        )
        assert policy.grn == grn
        assert policy.org_id == org_id
        assert len(policy.statements) == 1
        assert policy.resource_type == ResourceType.POLICY

    def test_policy_is_immutable(self, org_id: str):
        """Policy is frozen and immutable."""
        grn = GRN(
            org_id=org_id,
            resource_type=ResourceType.POLICY,
            resource_id="p1",
        )
        policy = Policy.create(
            grn=grn,
            org_id=org_id,
            created_by="admin",
            statements=[],
        )
        with pytest.raises(ValidationError):
            policy.org_id = "other"

    def test_policy_with_multiple_statements(self, org_id: str):
        """Policy with multiple statements."""
        grn = GRN(
            org_id=org_id,
            resource_type=ResourceType.POLICY,
            resource_id="multi",
        )
        stmts = [
            PolicyStatement(
                effect=Effect.ALLOW,
                principal_match="grn:org:user/*:*",
                action_match="read",
                resource_match="*",
            ),
            PolicyStatement(
                effect=Effect.DENY,
                principal_match="grn:org:user/contractor:*",
                action_match="admin:*",
                resource_match="*",
            ),
        ]
        policy = Policy.create(
            grn=grn,
            org_id=org_id,
            created_by="admin",
            statements=stmts,
        )
        assert len(policy.statements) == 2

    def test_policy_with_labels_and_metadata(self, org_id: str):
        """Policy can have labels and metadata."""
        grn = GRN(
            org_id=org_id,
            resource_type=ResourceType.POLICY,
            resource_id="labeled",
        )
        policy = Policy.create(
            grn=grn,
            org_id=org_id,
            created_by="admin",
            statements=[],
            labels={"env": "production", "team": "security"},
            metadata={"description": "Production policy"},
        )
        assert policy.labels["env"] == "production"
        assert policy.metadata["description"] == "Production policy"
