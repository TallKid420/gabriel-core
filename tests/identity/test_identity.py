"""Comprehensive tests for Principal and TokenService."""
import pytest
from datetime import datetime, timedelta

from gabriel.identity import (
    PrincipalID,
    PrincipalType,
    PrincipalStatus,
    Capability,
    Principal,
    Token,
    TokenPayload,
    KeyManager,
    TokenService,
    InvalidPrincipalIDError,
    TokenGenerationError,
    InvalidSignatureError,
    ExpiredTokenError,
    InvalidOrgError,
)


class TestPrincipalID:
    """Tests for PrincipalID parsing and formatting."""

    def test_principal_id_creation(self):
        """Test creating a PrincipalID."""
        pid = PrincipalID(
            org_id="acme",
            principal_type="user",
            principal_identifier="alice",
        )
        assert str(pid) == "principal://acme/user/alice"

    def test_principal_id_parse(self):
        """Test parsing a PrincipalID string."""
        pid_str = "principal://acme/agent/bot-01"
        pid = PrincipalID.parse(pid_str)
        assert pid.org_id == "acme"
        assert pid.principal_type == "agent"
        assert pid.principal_identifier == "bot-01"

    def test_principal_id_parse_invalid_scheme(self):
        """Test parsing fails with invalid scheme."""
        with pytest.raises(InvalidPrincipalIDError):
            PrincipalID.parse("actor://acme/user/alice")

    def test_principal_id_parse_invalid_format(self):
        """Test parsing fails with wrong number of parts."""
        with pytest.raises(InvalidPrincipalIDError):
            PrincipalID.parse("principal://acme/user")

    def test_principal_id_immutable(self):
        """Test PrincipalID is immutable."""
        pid = PrincipalID(
            org_id="acme",
            principal_type="user",
            principal_identifier="alice",
        )
        with pytest.raises(Exception):  # frozen dataclass
            pid.org_id = "other"


class TestPrincipal:
    """Tests for Principal creation and capabilities."""

    def test_principal_creation(self):
        """Test creating a Principal."""
        pid = PrincipalID(org_id="acme", principal_type="user", principal_identifier="alice")
        principal = Principal(
            id=pid,
            organization_id="acme",
            principal_type=PrincipalType.USER,
            display_name="Alice",
            capabilities={Capability.AUTHENTICATE, Capability.READ_RESOURCE},
        )
        assert principal.display_name == "Alice"
        assert principal.is_active()
        assert principal.can(Capability.AUTHENTICATE)

    def test_principal_capabilities_check(self):
        """Test capability checking."""
        pid = PrincipalID(org_id="acme", principal_type="agent", principal_identifier="bot")
        principal = Principal(
            id=pid,
            organization_id="acme",
            principal_type=PrincipalType.AGENT,
            display_name="Bot",
            capabilities={Capability.EXECUTE_WORKFLOW, Capability.CALL_TOOL},
        )
        assert principal.can(Capability.EXECUTE_WORKFLOW)
        assert not principal.can(Capability.MANAGE_PRINCIPALS)

    def test_principal_status(self):
        """Test principal status checking."""
        pid = PrincipalID(org_id="acme", principal_type="user", principal_identifier="bob")
        principal = Principal(
            id=pid,
            organization_id="acme",
            principal_type=PrincipalType.USER,
            display_name="Bob",
            status=PrincipalStatus.SUSPENDED,
        )
        assert not principal.is_active()
        assert principal.status == PrincipalStatus.SUSPENDED

    def test_principal_immutable(self):
        """Test Principal is immutable."""
        pid = PrincipalID(org_id="acme", principal_type="user", principal_identifier="alice")
        principal = Principal(
            id=pid,
            organization_id="acme",
            principal_type=PrincipalType.USER,
            display_name="Alice",
        )
        with pytest.raises(Exception):  # frozen Pydantic model
            principal.display_name = "Changed"


class TestTokenService:
    """Tests for token generation and verification."""

    @pytest.fixture
    def key_manager(self):
        """Fixture: Generate keys for testing."""
        return KeyManager()

    @pytest.fixture
    def token_service(self, key_manager):
        """Fixture: TokenService with test keys."""
        return TokenService(key_manager, token_expiry_seconds=3600)

    @pytest.fixture
    def principal(self):
        """Fixture: A sample principal."""
        pid = PrincipalID(org_id="acme", principal_type="user", principal_identifier="alice")
        return Principal(
            id=pid,
            organization_id="acme",
            principal_type=PrincipalType.USER,
            display_name="Alice",
            capabilities={Capability.AUTHENTICATE, Capability.READ_RESOURCE},
        )

    def test_token_issue(self, token_service, principal):
        """Test issuing a token for a principal."""
        token = token_service.issue(principal)
        assert isinstance(token, Token)
        assert token.value  # non-empty JWT string
        assert token.issued_at is not None
        assert token.expires_at > token.issued_at

    def test_token_verify(self, token_service, principal):
        """Test verifying a valid token."""
        token = token_service.issue(principal)
        payload = token_service.verify(token)

        assert isinstance(payload, TokenPayload)
        assert payload.principal_id == str(principal.id)
        assert payload.organization_id == "acme"
        assert payload.principal_type == "user"
        assert payload.display_name == "Alice"
        assert "authenticate" in payload.capabilities
        assert "read_resource" in payload.capabilities

    def test_token_verify_string(self, token_service, principal):
        """Test verifying a token from string."""
        token = token_service.issue(principal)
        payload = token_service.verify(token.value)

        assert payload.principal_id == str(principal.id)

    def test_token_roundtrip(self, token_service, principal):
        """Test the full flow: principal → token → verify → recover principal."""
        # Issue
        token = token_service.issue(principal)

        # Verify
        verified = token_service.verify(token)

        # Assert recovered principal info matches
        assert verified.principal_id == str(principal.id)
        assert verified.organization_id == principal.organization_id
        assert verified.display_name == principal.display_name

    def test_invalid_signature(self, principal):
        """Test that tampering with the token fails verification."""
        key_manager_1 = KeyManager()
        token_service_1 = TokenService(key_manager_1)

        key_manager_2 = KeyManager()  # Different key
        token_service_2 = TokenService(key_manager_2)

        # Issue with key 1
        token = token_service_1.issue(principal)

        # Try to verify with key 2 (wrong key)
        with pytest.raises(InvalidSignatureError):
            token_service_2.verify(token)

    def test_expired_token(self, principal):
        """Test that expired tokens fail verification."""
        key_manager = KeyManager()
        # Very short expiry
        token_service = TokenService(key_manager, token_expiry_seconds=-1)

        token = token_service.issue(principal)
        # Token is already expired due to negative TTL

        with pytest.raises(ExpiredTokenError):
            token_service.verify(token)

    def test_wrong_org(self, token_service, principal):
        """Test that verifying with wrong org_id fails."""
        token = token_service.issue(principal)

        with pytest.raises(InvalidOrgError):
            token_service.verify(token, organization_id="wrong-org")

    def test_correct_org(self, token_service, principal):
        """Test that verifying with correct org_id succeeds."""
        token = token_service.issue(principal)
        payload = token_service.verify(token, organization_id="acme")

        assert payload.organization_id == "acme"

    def test_system_principal(self):
        """Test creating a system agent principal."""
        pid = PrincipalID(
            org_id="system",
            principal_type="system_agent",
            principal_identifier="event-bus",
        )
        principal = Principal(
            id=pid,
            organization_id="system",
            principal_type=PrincipalType.SYSTEM_AGENT,
            display_name="Event Bus System Agent",
            capabilities={
                Capability.AUTHENTICATE,
                Capability.EXECUTE_WORKFLOW,
                Capability.MANAGE_PRINCIPALS,
            },
        )
        assert principal.principal_type == PrincipalType.SYSTEM_AGENT
        assert principal.can(Capability.MANAGE_PRINCIPALS)

    def test_service_account_principal(self):
        """Test creating a service account principal."""
        pid = PrincipalID(
            org_id="acme",
            principal_type="service_account",
            principal_identifier="ci-deploy",
        )
        principal = Principal(
            id=pid,
            organization_id="acme",
            principal_type=PrincipalType.SERVICE_ACCOUNT,
            display_name="CI/CD Deployment Account",
            capabilities={
                Capability.READ_RESOURCE,
                Capability.WRITE_RESOURCE,
                Capability.EXECUTE_WORKFLOW,
            },
        )
        assert principal.principal_type == PrincipalType.SERVICE_ACCOUNT
        assert not principal.can(Capability.MANAGE_POLICIES)
