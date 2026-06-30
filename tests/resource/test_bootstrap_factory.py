"""Tests for Core Bootstrap and Factory Pattern (ADR-009).

This test suite validates that:
1. Resources are registered uniformly through bootstrap
2. Creation is routed through ResourceFactory
3. Uniform identifier minting and defaults are applied
4. Both Organization and Principal use the canonical path
"""

import pytest
from gabriel.resource.registry import ResourceRegistry, registry
from gabriel.resource.factory import ResourceFactory
from gabriel.resource.bootstrap import register_core_resource_types
from gabriel.identity.bootstrap import register_identity_resource_types
from gabriel.organization.models import Organization
from gabriel.identity.principal import Principal
from gabriel.identity.principal_id import PrincipalID
from gabriel.identity.models import PrincipalType, PrincipalStatus, Capability
from gabriel.resource.models import ResourceState
from gabriel.resource.exceptions import ResourceTypeNotRegisteredError, DuplicateResourceTypeError


class TestCoreBootstrap:
    """Test that bootstrap registers all core resource types."""

    def test_register_core_types_is_idempotent(self):
        """Calling register_core_resource_types multiple times should not raise."""
        test_registry = ResourceRegistry()
        
        # First call should succeed
        register_core_resource_types(test_registry)
        assert test_registry.is_registered("organization")
        assert test_registry.is_registered("principal")
        
        # Second call should also succeed (idempotent)
        register_core_resource_types(test_registry)
        assert test_registry.is_registered("organization")
        assert test_registry.is_registered("principal")

    def test_register_organization_type(self):
        """Organization should be registered with correct metadata."""
        test_registry = ResourceRegistry()
        register_core_resource_types(test_registry)
        
        descriptor = test_registry.get_descriptor("organization")
        assert descriptor is not None
        assert descriptor.type_name == "organization"
        assert descriptor.version == "1.0"
        assert descriptor.model == Organization
        assert "core" in descriptor.tags
        assert "tenancy" in descriptor.tags

    def test_register_principal_type(self):
        """Principal should be registered with correct metadata."""
        test_registry = ResourceRegistry()
        register_core_resource_types(test_registry)
        
        descriptor = test_registry.get_descriptor("principal")
        assert descriptor is not None
        assert descriptor.type_name == "principal"
        assert descriptor.version == "1.0"
        assert descriptor.model == Principal
        assert "identity" in descriptor.tags
        assert "core" in descriptor.tags

    def test_identity_bootstrap_standalone(self):
        """Identity bootstrap should work independently."""
        test_registry = ResourceRegistry()
        register_identity_resource_types(test_registry)
        
        assert test_registry.is_registered("principal")
        descriptor = test_registry.get_descriptor("principal")
        assert descriptor.model == Principal


class TestFactoryResourceCreation:
    """Test that ResourceFactory creates resources uniformly."""

    @pytest.fixture
    def test_registry(self):
        """Create a test registry with core types registered."""
        reg = ResourceRegistry()
        register_core_resource_types(reg)
        return reg

    @pytest.fixture
    def factory(self, test_registry):
        """Create factory with test registry."""
        return ResourceFactory(test_registry)

    def test_create_organization_through_factory(self, factory):
        """Organization should be creatable through factory."""
        from gabriel.resource.grn import GRN
        
        org_id = "acme"
        grn = GRN.generate(org_id, "organization")
        
        org = factory.create(
            "organization",
            grn=grn,
            org_id=org_id,
            display_name="Acme Corp",
            state=ResourceState.ACTIVE,
            created_by="system",
            updated_by="system",
        )
        
        assert isinstance(org, Organization)
        assert org.org_id == "acme"
        assert org.display_name == "Acme Corp"
        assert org.state == ResourceState.ACTIVE

    def test_create_principal_through_factory(self, factory):
        """Principal should be creatable through factory."""
        principal_id = PrincipalID(
            org_id="acme",
            principal_type="user",
            principal_identifier="alice",
        )
        
        principal = factory.create(
            "principal",
            id=principal_id,
            organization_id="acme",
            principal_type=PrincipalType.USER,
            display_name="Alice",
            status=PrincipalStatus.ACTIVE,
            capabilities={Capability.AUTHENTICATE, Capability.READ_RESOURCE},
        )
        
        assert isinstance(principal, Principal)
        assert str(principal.id) == "principal://acme/user/alice"
        assert principal.display_name == "Alice"
        assert principal.status == PrincipalStatus.ACTIVE
        assert Capability.AUTHENTICATE in principal.capabilities

    def test_factory_raises_for_unregistered_type(self, factory):
        """Factory should raise for unregistered resource types."""
        with pytest.raises(ResourceTypeNotRegisteredError):
            factory.create("unknown_type", some_param="value")

    def test_organization_created_uniformly(self, factory):
        """Multiple organizations created through factory should have consistent structure."""
        from gabriel.resource.grn import GRN
        
        orgs = []
        for i in range(3):
            org_id = f"org-{i}"
            grn = GRN.generate(org_id, "organization")
            
            org = factory.create(
                "organization",
                grn=grn,
                org_id=org_id,
                display_name=f"Organization {i}",
                state=ResourceState.ACTIVE,
                created_by="system",
                updated_by="system",
            )
            orgs.append(org)
        
        # All should have consistent structure
        for org in orgs:
            assert isinstance(org, Organization)
            assert org.state == ResourceState.ACTIVE
            assert org.version == 1

    def test_principal_created_uniformly(self, factory):
        """Multiple principals created through factory should have consistent structure."""
        principals = []
        for i in range(3):
            pid = PrincipalID(
                org_id="acme",
                principal_type="agent",
                principal_identifier=f"bot-{i}",
            )
            
            principal = factory.create(
                "principal",
                id=pid,
                organization_id="acme",
                principal_type=PrincipalType.AGENT,
                display_name=f"Bot {i}",
                status=PrincipalStatus.ACTIVE,
            )
            principals.append(principal)
        
        # All should have consistent structure
        for principal in principals:
            assert isinstance(principal, Principal)
            assert principal.organization_id == "acme"
            assert principal.status == PrincipalStatus.ACTIVE


class TestBootstrapIntegration:
    """Test end-to-end bootstrap and factory integration."""

    def test_full_bootstrap_and_factory_workflow(self):
        """Test complete workflow: bootstrap → registry → factory → create."""
        from gabriel.resource.grn import GRN
        
        # Step 1: Bootstrap (typically done once at app startup)
        test_registry = ResourceRegistry()
        register_core_resource_types(test_registry)
        
        # Step 2: Create factory
        factory = ResourceFactory(test_registry)
        
        # Step 3: Create Organization
        org_grn = GRN.generate("acme", "organization")
        org = factory.create(
            "organization",
            grn=org_grn,
            org_id="acme",
            display_name="Acme Corporation",
            state=ResourceState.ACTIVE,
            created_by="admin",
            updated_by="admin",
        )
        
        # Step 4: Create Principal
        principal_id = PrincipalID(
            org_id="acme",
            principal_type="user",
            principal_identifier="alice",
        )
        principal = factory.create(
            "principal",
            id=principal_id,
            organization_id="acme",
            principal_type=PrincipalType.USER,
            display_name="Alice Smith",
            status=PrincipalStatus.ACTIVE,
            capabilities={Capability.AUTHENTICATE},
        )
        
        # Verify both created uniformly
        assert org.org_id == "acme"
        assert org.display_name == "Acme Corporation"
        assert str(principal.id) == "principal://acme/user/alice"
        assert principal.display_name == "Alice Smith"
        
        # Both are registered types
        assert test_registry.is_registered("organization")
        assert test_registry.is_registered("principal")

    def test_bootstrap_via_global_registry(self):
        """Test bootstrap using global registry."""
        # This tests that the global registry works
        # (In production, this happens once at startup)
        descriptor = registry.get_descriptor("organization")
        if descriptor is not None:
            # If already registered, verify it
            assert descriptor.model == Organization
            assert "core" in descriptor.tags


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
