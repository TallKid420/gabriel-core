"""Milestone 7 checklist tests: Type Registry & Resource Factory."""

import pytest

from gabriel.identity.principal import Principal
from gabriel.organization.models import Organization
from gabriel.policy.models import Policy
from gabriel.resource.descriptor import ResourceDescriptor
from gabriel.resource.exceptions import (
    DuplicateResourceTypeError,
    ResourceTypeNotRegisteredError,
)
from gabriel.resource.factory import ResourceFactory
from gabriel.resource.grn import GRN
from gabriel.resource.lifecycle import LifecycleManager
from gabriel.resource.models import ResourceType
from gabriel.resource.registry import ResourceRegistry


@pytest.fixture
def org_id() -> str:
    return "org-123"


@pytest.fixture
def registry() -> ResourceRegistry:
    return ResourceRegistry()


def test_register_resource(registry: ResourceRegistry) -> None:
    registry.register(Organization)
    registry.register(Policy)
    registry.register(Principal)

    assert registry.is_registered("organization")
    assert registry.is_registered("policy")
    assert registry.is_registered("principal")


def test_duplicate_registration(registry: ResourceRegistry) -> None:
    registry.register(Organization)
    with pytest.raises(DuplicateResourceTypeError):
        registry.register(Organization)


def test_factory_creation(registry: ResourceRegistry, org_id: str) -> None:
    registry.register(Organization)
    factory = ResourceFactory(registry)

    org = factory.create(
        "organization",
        grn=GRN(
            org_id=org_id,
            resource_type=ResourceType.ORGANIZATION,
            resource_id="org-1",
        ),
        org_id=org_id,
        created_by="admin",
        updated_by="admin",
        display_name="Acme",
    )

    assert isinstance(org, Organization)
    assert org.display_name == "Acme"


def test_serializer_roundtrip(registry: ResourceRegistry, org_id: str) -> None:
    registry.register(Organization)
    serializer = registry.get_serializer("organization")

    original = Organization(
        grn=GRN(
            org_id=org_id,
            resource_type=ResourceType.ORGANIZATION,
            resource_id="org-1",
        ),
        org_id=org_id,
        resource_type=ResourceType.ORGANIZATION,
        created_by="admin",
        updated_by="admin",
        display_name="Roundtrip",
    )

    payload = serializer.serialize(original)
    restored = serializer.deserialize(payload)

    assert restored == original


def test_validator_called(registry: ResourceRegistry, org_id: str) -> None:
    called = {"count": 0}

    def _validator(_: Organization) -> bool:
        called["count"] += 1
        return True

    descriptor = ResourceDescriptor(
        type_name="organization",
        version="1.0",
        model=Organization,
        lifecycle_class=LifecycleManager,
        description="organization",
        capabilities=frozenset(),
        validator_fn=_validator,
    )
    registry.register(descriptor)

    org = Organization(
        grn=GRN(
            org_id=org_id,
            resource_type=ResourceType.ORGANIZATION,
            resource_id="org-1",
        ),
        org_id=org_id,
        resource_type=ResourceType.ORGANIZATION,
        created_by="admin",
        updated_by="admin",
        display_name="Valid",
    )

    assert registry.get_validator("organization").validate(org) is True
    assert called["count"] == 1


def test_descriptor_lookup(registry: ResourceRegistry) -> None:
    registry.register(Organization)

    descriptor = registry.get_descriptor("organization")

    assert descriptor is not None
    assert descriptor.type_name == "organization"


def test_unknown_resource(registry: ResourceRegistry) -> None:
    factory = ResourceFactory(registry)

    with pytest.raises(ResourceTypeNotRegisteredError):
        factory.create("organization")


def test_versioning(registry: ResourceRegistry) -> None:
    descriptor = ResourceDescriptor(
        type_name="organization",
        version="2.1",
        model=Organization,
        lifecycle_class=LifecycleManager,
        description="organization",
        capabilities=frozenset(),
    )

    registry.register(descriptor)

    stored = registry.get_descriptor("organization")
    assert stored is not None
    assert stored.version == "2.1"
