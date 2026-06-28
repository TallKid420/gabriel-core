"""Tests for resource registry, factory, serializer, and validator."""
import pytest
from datetime import datetime, timezone

from gabriel.resource.descriptor import ResourceDescriptor
from gabriel.resource.registry import ResourceRegistry
from gabriel.resource.factory import ResourceFactory
from gabriel.resource.validators import ResourceValidator
from gabriel.resource.serializer import ResourceSerializer
from gabriel.resource.models import ResourceType, ResourceState
from gabriel.resource.grn import GRN
from gabriel.resource.lifecycle import LifecycleManager
from gabriel.resource.exceptions import (
    DuplicateResourceTypeError,
    ResourceTypeNotRegisteredError,
    ResourceFactoryError,
    ResourceValidationError,
    ResourceSerializationError,
)
from gabriel.organization.models import Organization
from gabriel.policy.models import Policy, PolicyStatement, Effect
from gabriel.identity.principal import Principal
from gabriel.identity.models import PrincipalType


@pytest.fixture
def org_id() -> str:
    return "org-123"


@pytest.fixture
def registry() -> ResourceRegistry:
    """Fresh registry for each test."""
    return ResourceRegistry()


class TestResourceDescriptor:
    """Tests for ResourceDescriptor metadata."""
    
    def test_descriptor_creation(self):
        """Descriptors capture complete resource type metadata."""
        descriptor = ResourceDescriptor(
            type_name="organization",
            version="1.0",
            model=Organization,
            lifecycle_class=LifecycleManager,
            description="An organization tenant",
            capabilities=frozenset(["read", "write"]),
        )
        
        assert descriptor.type_name == "organization"
        assert descriptor.version == "1.0"
        assert descriptor.model == Organization
        assert descriptor.lifecycle_class == LifecycleManager
        assert "read" in descriptor.capabilities
    
    def test_descriptor_with_tags(self):
        """Descriptors can have categorization tags."""
        descriptor = ResourceDescriptor(
            type_name="organization",
            version="1.0",
            model=Organization,
            lifecycle_class=LifecycleManager,
            description="An organization",
            capabilities=frozenset(),
            tags=frozenset(["core", "tenant-isolated"]),
        )
        
        assert "core" in descriptor.tags
        assert "tenant-isolated" in descriptor.tags
    
    def test_descriptor_hashable(self):
        """Descriptors are hashable."""
        desc1 = ResourceDescriptor(
            type_name="organization",
            version="1.0",
            model=Organization,
            lifecycle_class=LifecycleManager,
            description="Org",
            capabilities=frozenset(),
        )
        desc2 = ResourceDescriptor(
            type_name="organization",
            version="1.0",
            model=Organization,
            lifecycle_class=LifecycleManager,
            description="Org",
            capabilities=frozenset(),
        )
        
        # Same type names should be equal
        assert desc1 == desc2
        assert hash(desc1) == hash(desc2)


class TestResourceRegistry:
    """Tests for the resource registry."""
    
    def test_register_descriptor(self, registry: ResourceRegistry):
        """Registry stores resource descriptors."""
        descriptor = ResourceDescriptor(
            type_name="organization",
            version="1.0",
            model=Organization,
            lifecycle_class=LifecycleManager,
            description="Organization",
            capabilities=frozenset(["read"]),
        )
        
        registry.register(descriptor)
        
        assert registry.is_registered("organization")
        assert registry.get_descriptor("organization") == descriptor
    
    def test_duplicate_registration_error(self, registry: ResourceRegistry):
        """Cannot register same type twice."""
        descriptor = ResourceDescriptor(
            type_name="organization",
            version="1.0",
            model=Organization,
            lifecycle_class=LifecycleManager,
            description="Organization",
            capabilities=frozenset(),
        )
        
        registry.register(descriptor)
        
        with pytest.raises(DuplicateResourceTypeError):
            registry.register(descriptor)
    
    def test_register_from_class(self, registry: ResourceRegistry):
        """Can register resource type from class (convenience)."""
        descriptor = registry.register_from_class(
            model_class=Organization,
            lifecycle_class=LifecycleManager,
            version="1.0",
            description="Test Organization",
            capabilities=frozenset(["read", "write"]),
        )
        
        assert descriptor.type_name == "organization"
        assert registry.is_registered("organization")
    
    def test_get_nonexistent_descriptor(self, registry: ResourceRegistry):
        """Getting nonexistent descriptor returns None."""
        assert registry.get_descriptor("nonexistent") is None
    
    def test_all_descriptors(self, registry: ResourceRegistry):
        """Can retrieve all registered descriptors."""
        desc1 = ResourceDescriptor(
            type_name="organization",
            version="1.0",
            model=Organization,
            lifecycle_class=LifecycleManager,
            description="Org",
            capabilities=frozenset(),
        )
        desc2 = ResourceDescriptor(
            type_name="policy",
            version="1.0",
            model=Policy,
            lifecycle_class=LifecycleManager,
            description="Policy",
            capabilities=frozenset(),
        )
        
        registry.register(desc1)
        registry.register(desc2)
        
        descriptors = registry.all_descriptors()
        assert len(descriptors) == 2
        assert desc1 in descriptors
        assert desc2 in descriptors
    
    def test_all_types(self, registry: ResourceRegistry):
        """Can get all registered type names."""
        registry.register_from_class(Organization, LifecycleManager)
        registry.register_from_class(Policy, LifecycleManager)
        
        types = registry.all_types()
        assert "organization" in types
        assert "policy" in types
    
    def test_unregister(self, registry: ResourceRegistry):
        """Can unregister a resource type."""
        registry.register_from_class(Organization, LifecycleManager)
        
        assert registry.is_registered("organization")
        assert registry.unregister("organization") is True
        assert not registry.is_registered("organization")
    
    def test_unregister_nonexistent(self, registry: ResourceRegistry):
        """Unregistering nonexistent type returns False."""
        assert registry.unregister("nonexistent") is False


class TestResourceFactory:
    """Tests for the resource factory."""
    
    def test_factory_create_via_model_create_method(self, registry: ResourceRegistry, org_id: str):
        """Factory uses model's create() method if available."""
        registry.register_from_class(Organization, LifecycleManager)
        factory = ResourceFactory(registry)
        
        grn = GRN(
            org_id=org_id,
            resource_type=ResourceType.ORGANIZATION,
            resource_id="org1",
        )
        
        org = factory.create(
            "organization",
            grn=grn,
            org_id=org_id,
            created_by="admin",
            updated_by="admin",
            display_name="Test Org",
        )
        
        assert org.display_name == "Test Org"
        assert org.org_id == org_id
    
    def test_factory_unregistered_type_error(self, registry: ResourceRegistry):
        """Factory raises error for unregistered type."""
        factory = ResourceFactory(registry)
        
        with pytest.raises(ResourceTypeNotRegisteredError):
            factory.create("nonexistent")
    
    def test_factory_create_from_dict(self, registry: ResourceRegistry, org_id: str):
        """Factory can create from dictionary (deserialization)."""
        registry.register_from_class(Organization, LifecycleManager)
        factory = ResourceFactory(registry)
        
        grn = GRN(
            org_id=org_id,
            resource_type=ResourceType.ORGANIZATION,
            resource_id="org1",
        )
        
        data = {
            "grn": grn,
            "org_id": org_id,
            "resource_type": ResourceType.ORGANIZATION,
            "state": ResourceState.DRAFT,
            "version": 1,
            "created_by": "admin",
            "updated_by": "admin",
            "display_name": "From Dict Org",
        }
        
        org = factory.create_from_dict("organization", data)
        assert org.display_name == "From Dict Org"


class TestResourceValidator:
    """Tests for resource validation."""
    
    def test_validator_validates_type(self, registry: ResourceRegistry, org_id: str):
        """Validator checks correct type."""
        descriptor = registry.register_from_class(Organization, LifecycleManager)
        validator = registry.get_validator("organization")
        
        grn = GRN(
            org_id=org_id,
            resource_type=ResourceType.ORGANIZATION,
            resource_id="org1",
        )
        
        org = Organization(
            grn=grn,
            org_id=org_id,
            resource_type=ResourceType.ORGANIZATION,
            created_by="admin",
            updated_by="admin",
            display_name="Test",
        )
        
        assert validator.validate(org) is True
    
    def test_validator_rejects_wrong_type(self, registry: ResourceRegistry):
        """Validator rejects wrong type."""
        descriptor = registry.register_from_class(Organization, LifecycleManager)
        validator = registry.get_validator("organization")
        
        with pytest.raises(ResourceValidationError):
            validator.validate("not an organization")


class TestResourceSerializer:
    """Tests for resource serialization."""
    
    def test_serializer_to_dict(self, registry: ResourceRegistry, org_id: str):
        """Serializer converts resource to dict."""
        registry.register_from_class(Organization, LifecycleManager)
        serializer = registry.get_serializer("organization")
        
        grn = GRN(
            org_id=org_id,
            resource_type=ResourceType.ORGANIZATION,
            resource_id="org1",
        )
        
        org = Organization(
            grn=grn,
            org_id=org_id,
            resource_type=ResourceType.ORGANIZATION,
            created_by="admin",
            updated_by="admin",
            display_name="Test",
        )
        
        data = serializer.serialize(org)
        
        assert isinstance(data, dict)
        assert data["org_id"] == org_id
        assert data["display_name"] == "Test"
    
    def test_serializer_roundtrip(self, registry: ResourceRegistry, org_id: str):
        """Serializer roundtrip: resource → dict → resource."""
        registry.register_from_class(Organization, LifecycleManager)
        serializer = registry.get_serializer("organization")
        
        grn = GRN(
            org_id=org_id,
            resource_type=ResourceType.ORGANIZATION,
            resource_id="org1",
        )
        
        org_original = Organization(
            grn=grn,
            org_id=org_id,
            resource_type=ResourceType.ORGANIZATION,
            created_by="admin",
            updated_by="admin",
            display_name="Original",
        )
        
        # Serialize to dict
        data = serializer.serialize(org_original)
        
        # Deserialize back
        org_restored = serializer.deserialize(data)
        
        assert org_restored.org_id == org_original.org_id
        assert org_restored.display_name == org_original.display_name
    
    def test_serializer_to_json(self, registry: ResourceRegistry, org_id: str):
        """Serializer converts to JSON."""
        registry.register_from_class(Organization, LifecycleManager)
        serializer = registry.get_serializer("organization")
        
        grn = GRN(
            org_id=org_id,
            resource_type=ResourceType.ORGANIZATION,
            resource_id="org1",
        )
        
        org = Organization(
            grn=grn,
            org_id=org_id,
            resource_type=ResourceType.ORGANIZATION,
            created_by="admin",
            updated_by="admin",
            display_name="Test",
        )
        
        json_str = serializer.to_json(org)
        
        assert isinstance(json_str, str)
        assert "Test" in json_str
        assert org_id in json_str
    
    def test_serializer_from_json(self, registry: ResourceRegistry, org_id: str):
        """Serializer restores from JSON."""
        registry.register_from_class(Organization, LifecycleManager)
        serializer = registry.get_serializer("organization")
        
        grn = GRN(
            org_id=org_id,
            resource_type=ResourceType.ORGANIZATION,
            resource_id="org1",
        )
        
        org_original = Organization(
            grn=grn,
            org_id=org_id,
            resource_type=ResourceType.ORGANIZATION,
            created_by="admin",
            updated_by="admin",
            display_name="Original",
        )
        
        json_str = serializer.to_json(org_original)
        org_restored = serializer.from_json(json_str)
        
        assert org_restored.display_name == "Original"


class TestUniversalResourceModel:
    """Integration tests showing the complete URM in action."""
    
    def test_register_multiple_resources(self, registry: ResourceRegistry):
        """Registry handles multiple resource types without if/else chains."""
        registry.register_from_class(Organization, LifecycleManager, tags=frozenset(["core"]))
        registry.register_from_class(Policy, LifecycleManager, tags=frozenset(["security"]))
        
        assert registry.is_registered("organization")
        assert registry.is_registered("policy")
        assert len(registry.all_types()) == 2
    
    def test_factory_without_if_else(self, registry: ResourceRegistry, org_id: str):
        """Factory creates resources without any if/else chains."""
        # Register all types
        registry.register_from_class(Organization, LifecycleManager)
        registry.register_from_class(Policy, LifecycleManager)
        
        factory = ResourceFactory(registry)
        
        # Create without knowing the implementation details
        grn_org = GRN(
            org_id=org_id,
            resource_type=ResourceType.ORGANIZATION,
            resource_id="org1",
        )
        
        grn_policy = GRN(
            org_id=org_id,
            resource_type=ResourceType.POLICY,
            resource_id="policy1",
        )
        
        org = factory.create(
            "organization",
            grn=grn_org,
            org_id=org_id,
            created_by="admin",
            updated_by="admin",
            display_name="Test Org",
        )
        
        policy = factory.create(
            "policy",
            grn=grn_policy,
            org_id=org_id,
            created_by="admin",
            statements=[],
        )
        
        assert isinstance(org, Organization)
        assert isinstance(policy, Policy)
        # No if/else chain needed!
    
    def test_serialization_path_complete(self, registry: ResourceRegistry, org_id: str):
        """Complete serialization path: resource → dict → JSON → database → event."""
        registry.register_from_class(Organization, LifecycleManager)
        serializer = registry.get_serializer("organization")
        
        grn = GRN(
            org_id=org_id,
            resource_type=ResourceType.ORGANIZATION,
            resource_id="org1",
        )
        
        org = Organization(
            grn=grn,
            org_id=org_id,
            resource_type=ResourceType.ORGANIZATION,
            created_by="admin",
            updated_by="admin",
            display_name="Test",
        )
        
        # Path: resource → dict
        data = serializer.serialize(org)
        
        # Path: dict → JSON
        json_str = serializer.to_json(org)
        
        # Path: JSON → dict (simulating database retrieval)
        restored_data = serializer.deserialize(data)
        
        # Path: dict → resource (reconstructing)
        assert restored_data.display_name == org.display_name
