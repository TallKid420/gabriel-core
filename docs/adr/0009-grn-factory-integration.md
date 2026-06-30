# ADR-009 Implementation: GRN Factory Integration

**Date:** 2026-06-29
**Status:** ✅ IMPLEMENTED
**Milestone:** 8 (Resource Abstraction & Registry)

## Overview

ADR-009 establishes a canonical resource creation pattern through `ResourceFactory` to eliminate ad-hoc GRN and resource construction across the system. All resources (Organization, Principal, future: Policy, Agent, etc.) are now created uniformly through the factory, ensuring:

1. **Uniform identifier minting** - GRNs and other identifiers follow consistent rules
2. **Centralized defaults** - Each resource type has registered defaults
3. **Single source of truth** - Registry holds all resource metadata
4. **No if/else chains** - Everything data-driven from descriptors
5. **Testability** - Mock or substitute registry/factory in tests

## Implementation

### Bootstrap Architecture

The system uses two-level bootstrap:

```
Application Startup
    ↓
register_core_resource_types()
    ↓
  ├─ Registers Organization (via resource.bootstrap)
  └─ Registers Principal (via identity.bootstrap)
    ↓
ResourceFactory(registry)
    ↓
Service layers + Handlers create resources uniformly
```

### Core Files

#### 1. `src/gabriel/resource/bootstrap.py`
**Purpose:** Single entry point for resource registration

```python
def register_core_resource_types(target_registry=None):
    """Register Organization and Principal resources."""
    # Registers Organization
    registry.register(Organization, ...)
    
    # Registers Principal via identity bootstrap
    register_identity_resource_types(registry)
```

**Usage:**
```python
# In application startup (main.py or app initialization)
from gabriel.resource.bootstrap import register_core_resource_types
register_core_resource_types()  # Idempotent, safe to call multiple times
```

#### 2. `src/gabriel/identity/bootstrap.py`
**Purpose:** Register identity resources (Principal, future: User, Agent, ServiceAccount)

```python
def register_identity_resource_types(target_registry=None):
    """Register Principal as a resource type."""
    registry.register(
        Principal,
        description="Universal identity abstraction for all actors",
        version="1.0",
        tags=frozenset({"identity", "core"}),
    )
```

**Usage:**
```python
from gabriel.identity.bootstrap import register_identity_resource_types
register_identity_resource_types()
```

#### 3. `src/gabriel/resource/factory.py`
**Purpose:** Create resources uniformly from registry descriptors

```python
class ResourceFactory:
    def create(self, resource_type: str, **kwargs) -> Any:
        """Create a resource instance.
        
        Looks up type in registry, applies factory_fn or instantiation method.
        """
        descriptor = registry.get_descriptor(resource_type)
        return descriptor.model(**kwargs)  # or descriptor.factory_fn(**kwargs)
```

**Usage:**
```python
from gabriel.resource.factory import ResourceFactory
from gabriel.resource.registry import registry

factory = ResourceFactory(registry)

# Create Organization uniformly
org = factory.create(
    "organization",
    grn=GRN.generate("acme", "organization"),
    org_id="acme",
    display_name="Acme Corp",
    state=ResourceState.ACTIVE,
    created_by="admin",
)

# Create Principal uniformly
principal = factory.create(
    "principal",
    id=PrincipalID(org_id="acme", principal_type="user", principal_identifier="alice"),
    organization_id="acme",
    principal_type=PrincipalType.USER,
    display_name="Alice",
    status=PrincipalStatus.ACTIVE,
)
```

### Service Integration

Services now integrate the factory pattern:

#### OrganizationService (existing, already uses factory)
```python
class OrganizationService:
    def __init__(self, repository: OrganizationRepository):
        register_core_resource_types()  # Bootstrap once
        self.factory = ResourceFactory(registry)
    
    async def register_organization(self, display_name: str, created_by: str):
        # Create through factory (uniform path)
        org = self.factory.create("organization", ...)
        # Persist ORM representation
        return await self.repo.create(domain_to_orm(org))
```

#### PrincipalService (updated to use factory)
```python
class PrincipalService:
    def __init__(self, repository: PrincipalRepositoryProtocol):
        register_core_resource_types()  # Bootstrap once
        self.factory = ResourceFactory(registry)
    
    def register_principal(self, org_id: str, principal_type, ...):
        # Create through factory (uniform path)
        principal = self.factory.create("principal", ...)
        # Persist through repository
        return self.repo.create(principal)
```

### Event Handler Integration

Event handlers also use the factory:

#### CreateOrganizationHandler (existing, already uses factory)
```python
class CreateOrganizationHandler(Handler):
    def __init__(self, factory=None):
        register_core_resource_types()
        self.factory = factory or ResourceFactory(registry)
    
    async def handle(self, command: Command) -> list[Event]:
        # Create through factory (uniform path)
        org = self.factory.create(
            "organization",
            grn=GRN.generate(org_id=org_slug, resource_type="organization"),
            ...
        )
        # Emit event with created resource
        return [Event(type="organization_created", ...)]
```

## Benefits Realized

### Before ADR-009
```python
# Inconsistent creation patterns across codebase
# OrganizationService
grn = GRN.generate(org_slug, "organization")
org = Organization(grn=grn, org_id=org_slug, display_name=display_name, ...)

# CreateOrganizationHandler
grn = GRN.generate(org_id=org_slug, resource_type="organization")
org = Organization(grn=grn, org_id=org_slug, ...)

# Future PrincipalService (had ad-hoc construction)
principal = Principal(id=pid, organization_id=org_id, ...)
```

### After ADR-009
```python
# Consistent factory pattern everywhere
register_core_resource_types()
factory = ResourceFactory(registry)

# OrganizationService
org = factory.create("organization", grn=grn, org_id=org_slug, ...)

# CreateOrganizationHandler
org = factory.create("organization", grn=grn, org_id=org_slug, ...)

# PrincipalService
principal = factory.create("principal", id=pid, organization_id=org_id, ...)
```

## Extension Pattern

### Adding a New Resource Type

```python
# 1. Create bootstrap in appropriate module
# In src/gabriel/policy/bootstrap.py
from gabriel.policy.models import Policy

def register_policy_resource_types(target_registry=None):
    reg = target_registry or registry
    if not reg.is_registered("policy"):
        reg.register(Policy, description="...", version="1.0", ...)

# 2. Update core bootstrap to call it
# In src/gabriel/resource/bootstrap.py
def register_core_resource_types(target_registry=None):
    reg = target_registry or registry
    
    # Existing registrations
    reg.register(Organization, ...)
    register_identity_resource_types(reg)
    
    # Add new registration
    from gabriel.policy.bootstrap import register_policy_resource_types
    register_policy_resource_types(reg)

# 3. Use in services and handlers
service.factory.create("policy", ...)
```

### Custom Factory Functions

If a resource needs special construction logic:

```python
def policy_factory(**kwargs):
    """Custom factory for Policy with special defaults."""
    return Policy.with_defaults(**kwargs)

registry.register(
    Policy,
    factory_fn=policy_factory,
    description="...",
)

# Factory automatically uses custom factory_fn
policy = factory.create("policy", ...)
```

## Testing

Bootstrap and factory pattern is fully testable:

```python
def test_organization_creation_uniform():
    # Create test registry
    test_registry = ResourceRegistry()
    register_core_resource_types(test_registry)
    
    # Test factory with isolated registry
    factory = ResourceFactory(test_registry)
    org = factory.create("organization", ...)
    
    assert org.org_id == "acme"
    assert org.state == ResourceState.ACTIVE
```

## Files Changed

### Created
- `src/gabriel/identity/bootstrap.py` - Identity resource registration
- `src/gabriel/resource/factory_examples.py` - Usage documentation
- `tests/resource/test_bootstrap_factory.py` - Comprehensive test suite

### Modified
- `src/gabriel/resource/bootstrap.py` - Integrated identity bootstrap
- `src/gabriel/identity/__init__.py` - Exported bootstrap function
- `src/gabriel/identity/service.py` - Integrated factory pattern

## Verification

### Bootstrap Idempotency
```bash
# Safe to call multiple times
register_core_resource_types()
register_core_resource_types()  # No error
```

### Factory Creation
```bash
# Resources created uniformly
org = factory.create("organization", ...)
principal = factory.create("principal", ...)
```

### Registry Metadata
```bash
# All descriptors available
descriptor = registry.get_descriptor("organization")
assert descriptor.type_name == "organization"
assert descriptor.version == "1.0"
```

## Future Work

1. **Agent/Policy/Tool Resources** - Register User, Agent, SystemAgent, ServiceAccount, Policy, Tool types
2. **Custom Factory Functions** - Add factory_fn to descriptors for complex construction logic
3. **Validation Hooks** - Add validator_fn callbacks to descriptors
4. **Serialization** - Use serializer_fn from descriptors for uniform API responses
5. **Lifecycle Policies** - Different lifecycle managers per resource type

## Related ADRs

- **ADR-009** - GRN Factory Integration (this document)
- **ADR-001** - Principal Resource Mirroring (GRN links on Principal)
- **Milestone 7** - Runtime Import Rule (RuntimeRegistry pattern extends factory)
- **Milestone 3** - Identity Abstraction (Principal hierarchy)

## Conclusion

ADR-009 implementation creates a canonical, extensible pattern for resource creation throughout Gabriel. The factory pattern combined with registry-based metadata eliminates ad-hoc construction, enables testability, and provides a foundation for uniform behavior across all resource types.
