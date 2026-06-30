"""Tests for PEEL (Policy Enforcement & Evaluation Layer)."""
import pytest

from gabriel.policy.models import Policy, PolicyStatement, Effect
from gabriel.policy.engine import PolicyEngine, EvaluationRequest
from gabriel.policy.peel import PEEL
from gabriel.policy.exceptions import UnauthorizedError
from gabriel.resource.grn import GRN
from gabriel.resource.models import ResourceType


class TestPolicyEngine:
    """Test PolicyEngine evaluation logic."""

    def test_default_deny_empty_policies(self, policy_engine: PolicyEngine):
        """Default deny: no policies means deny everything."""
        request = EvaluationRequest(
            principal="principal:org:user/alice",
            action="read",
            resource="grn:org:doc/123",
        )
        assert policy_engine.evaluate(request) == Effect.DENY

    def test_explicit_allow(self, policy_engine: PolicyEngine, allow_all_policy: Policy):
        """Explicit allow: policy with ALLOW statement allows action."""
        policy_engine.add_policy(allow_all_policy)
        request = EvaluationRequest(
            principal="principal:org:user/alice",
            action="read",
            resource="grn:org:doc/123",
        )
        assert policy_engine.evaluate(request) == Effect.ALLOW

    def test_explicit_deny_overrides_allow(self, policy_engine: PolicyEngine):
        """Explicit deny overrides: DENY in any policy overrides ALLOWs."""
        # Add allow-all policy
        allow_stmt = PolicyStatement(
            effect=Effect.ALLOW,
            principal_match="*",
            action_match="*",
            resource_match="*",
        )
        allow_policy = Policy.create(
            grn=GRN(org_id="org", resource_type=ResourceType.POLICY, resource_id="allow"),
            org_id="org",
            created_by="admin",
            statements=[allow_stmt],
        )
        policy_engine.add_policy(allow_policy)

        # Add deny-admin policy
        deny_stmt = PolicyStatement(
            effect=Effect.DENY,
            principal_match="bad_user",
            action_match="*",
            resource_match="*",
        )
        deny_policy = Policy.create(
            grn=GRN(org_id="org", resource_type=ResourceType.POLICY, resource_id="deny"),
            org_id="org",
            created_by="admin",
            statements=[deny_stmt],
        )
        policy_engine.add_policy(deny_policy)

        # Bad user should be denied despite allow-all policy
        request = EvaluationRequest(
            principal="bad_user",
            action="write",
            resource="secret",
        )
        assert policy_engine.evaluate(request) == Effect.DENY

    def test_wildcard_principal_match(self, policy_engine: PolicyEngine, allow_all_policy: Policy):
        """Wildcard matching: * matches any principal."""
        policy_engine.add_policy(allow_all_policy)
        for principal in ["alice", "bob", "principal://org/agent/robot"]:
            request = EvaluationRequest(principal=principal, action="read", resource="r1")
            assert policy_engine.evaluate(request) == Effect.ALLOW

    def test_glob_principal_match(self, policy_engine: PolicyEngine):
        """Glob pattern matching: principal://org/user/* matches users."""
        stmt = PolicyStatement(
            effect=Effect.ALLOW,
            principal_match="principal://org/user/*",
            action_match="read",
            resource_match="*",
        )
        policy = Policy.create(
            grn=GRN(org_id="org", resource_type=ResourceType.POLICY, resource_id="p1"),
            org_id="org",
            created_by="admin",
            statements=[stmt],
        )
        policy_engine.add_policy(policy)

        # Should allow user
        req_user = EvaluationRequest(
            principal="principal://org/user/alice",
            action="read",
            resource="doc",
        )
        assert policy_engine.evaluate(req_user) == Effect.ALLOW

        # Should deny agent
        req_agent = EvaluationRequest(
            principal="principal://org/agent/bot",
            action="read",
            resource="doc",
        )
        assert policy_engine.evaluate(req_agent) == Effect.DENY

    def test_glob_action_match(self, policy_engine: PolicyEngine):
        """Glob pattern matching: identity:* matches identity actions."""
        stmt = PolicyStatement(
            effect=Effect.ALLOW,
            principal_match="*",
            action_match="identity:*",
            resource_match="*",
        )
        policy = Policy.create(
            grn=GRN(org_id="org", resource_type=ResourceType.POLICY, resource_id="p1"),
            org_id="org",
            created_by="admin",
            statements=[stmt],
        )
        policy_engine.add_policy(policy)

        # Should allow identity actions
        assert policy_engine.evaluate(
            EvaluationRequest(principal="u1", action="identity:create", resource="r1")
        ) == Effect.ALLOW

        # Should deny non-identity actions
        assert policy_engine.evaluate(
            EvaluationRequest(principal="u1", action="resource:delete", resource="r1")
        ) == Effect.DENY

    def test_glob_resource_match(self, policy_engine: PolicyEngine):
        """Glob pattern matching: grn:org:agent/*:* matches agents."""
        stmt = PolicyStatement(
            effect=Effect.ALLOW,
            principal_match="*",
            action_match="*",
            resource_match="grn:org:agent/*:*",
        )
        policy = Policy.create(
            grn=GRN(org_id="org", resource_type=ResourceType.POLICY, resource_id="p1"),
            org_id="org",
            created_by="admin",
            statements=[stmt],
        )
        policy_engine.add_policy(policy)

        # Should allow agent resources
        assert policy_engine.evaluate(
            EvaluationRequest(principal="u1", action="write", resource="grn:org:agent/bot1:1")
        ) == Effect.ALLOW

        # Should deny other resources
        assert policy_engine.evaluate(
            EvaluationRequest(principal="u1", action="write", resource="grn:org:user/alice:1")
        ) == Effect.DENY

    def test_evaluate_batch(self, policy_engine: PolicyEngine, allow_all_policy: Policy):
        """Batch evaluation: evaluate multiple requests at once."""
        policy_engine.add_policy(allow_all_policy)
        requests = [
            EvaluationRequest(principal=f"p{i}", action="a", resource=f"r{i}")
            for i in range(5)
        ]
        results = policy_engine.evaluate_batch(requests)
        assert all(r == Effect.ALLOW for r in results)

    def test_add_remove_policy(self, policy_engine: PolicyEngine, allow_all_policy: Policy):
        """Add/remove policies from engine."""
        assert len(policy_engine.policies) == 0

        policy_engine.add_policy(allow_all_policy)
        assert len(policy_engine.policies) == 1

        removed = policy_engine.remove_policy(str(allow_all_policy.grn))
        assert removed is True
        assert len(policy_engine.policies) == 0

    def test_remove_nonexistent_policy(self, policy_engine: PolicyEngine):
        """Remove policy that doesn't exist returns False."""
        removed = policy_engine.remove_policy("grn:org:policy/nonexistent:1")
        assert removed is False


class TestMultipleStatements:
    """Test evaluation with multiple statements in a policy."""

    def test_first_matching_allow_wins_for_allow(self, policy_engine: PolicyEngine):
        """First matching ALLOW statement wins (for allowing)."""
        # Two ALLOW statements, first one should apply
        stmts = [
            PolicyStatement(
                effect=Effect.ALLOW,
                principal_match="user1",
                action_match="read",
                resource_match="*",
            ),
            PolicyStatement(
                effect=Effect.ALLOW,
                principal_match="*",
                action_match="read",
                resource_match="*",
            ),
        ]
        policy = Policy.create(
            grn=GRN(org_id="org", resource_type=ResourceType.POLICY, resource_id="p1"),
            org_id="org",
            created_by="admin",
            statements=stmts,
        )
        policy_engine.add_policy(policy)

        # User1 should be allowed (first statement matches)
        assert policy_engine.evaluate(
            EvaluationRequest(principal="user1", action="read", resource="doc")
        ) == Effect.ALLOW

    def test_deny_short_circuits_evaluation(self, policy_engine: PolicyEngine):
        """DENY returns immediately without checking other policies."""
        stmts = [
            PolicyStatement(
                effect=Effect.ALLOW,
                principal_match="*",
                action_match="*",
                resource_match="*",
            ),
            PolicyStatement(
                effect=Effect.DENY,
                principal_match="admin",
                action_match="sensitive:*",
                resource_match="*",
            ),
        ]
        policy = Policy.create(
            grn=GRN(org_id="org", resource_type=ResourceType.POLICY, resource_id="p1"),
            org_id="org",
            created_by="admin",
            statements=stmts,
        )
        policy_engine.add_policy(policy)

        # ALLOW matches first, but DENY is more specific
        # Since both match, the engine should return DENY (it's checked after ALLOW)
        assert policy_engine.evaluate(
            EvaluationRequest(principal="admin", action="sensitive:delete", resource="secret")
        ) == Effect.DENY


class TestPEEL:
    """Test PEEL authorization wrapper."""

    @pytest.mark.asyncio
    async def test_authorize_allowed(self, execution_context, allow_all_policy: Policy):
        """PEEL authorize succeeds when allowed."""
        engine = PolicyEngine([allow_all_policy])
        peel = PEEL(engine)

        # Should not raise
        await peel.authorize(
            execution_context,
            "identity:create",
            "grn:org:user/alice:1",
        )

    @pytest.mark.asyncio
    async def test_authorize_denied(self, execution_context):
        """PEEL authorize raises UnauthorizedError when denied."""
        engine = PolicyEngine()  # Empty = deny everything
        peel = PEEL(engine)

        with pytest.raises(UnauthorizedError):
            await peel.authorize(
                execution_context,
                "identity:create",
                "grn:org:user/alice:1",
            )

    @pytest.mark.asyncio
    async def test_authorize_batch_allowed(self, execution_context, allow_all_policy: Policy):
        """PEEL batch authorize all allowed."""
        engine = PolicyEngine([allow_all_policy])
        peel = PEEL(engine)

        requests = [
            ("read", "grn:org:doc/1:1"),
            ("write", "grn:org:doc/2:1"),
            ("delete", "grn:org:doc/3:1"),
        ]

        # Should not raise
        await peel.authorize_batch(execution_context, requests)

    @pytest.mark.asyncio
    async def test_authorize_batch_denied_first(self, execution_context):
        """PEEL batch authorize stops on first denial."""
        engine = PolicyEngine()  # Empty = deny everything
        peel = PEEL(engine)

        requests = [
            ("read", "grn:org:doc/1:1"),
            ("write", "grn:org:doc/2:1"),
        ]

        with pytest.raises(UnauthorizedError):
            await peel.authorize_batch(execution_context, requests)

    @pytest.mark.asyncio
    async def test_unauthorized_error_message(self, execution_context):
        """UnauthorizedError includes details."""
        engine = PolicyEngine()  # Empty = deny everything
        peel = PEEL(engine)

        with pytest.raises(UnauthorizedError) as exc_info:
            await peel.authorize(
                execution_context,
                "admin:delete",
                "grn:org:system/config:1",
            )

        error_msg = str(exc_info.value)
        assert "admin:delete" in error_msg
        assert "grn:org:system/config:1" in error_msg