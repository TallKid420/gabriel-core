"""Factory Usage Examples: Creating Resources Uniformly

This module demonstrates the canonical resource creation pattern via ResourceFactory.
It ensures uniform identifier minting, default handling, and lifecycle management
across all resource types (satisfies ADR-009: GRN Factory Integration).

BEFORE (ad-hoc construction):
    In OrganizationService:
        grn = GRN.generate(org_slug, "organization")
        org = Organization(grn=grn, org_id=org_slug, display_name=display_name, ...)
    
    In Principal creation:
        principal = Principal(id=pid, organization_id=org_id, ...)
    
    Different construction patterns → inconsistent defaults, duplicated logic

AFTER (factory pattern):
    from gabriel.resource.bootstrap import register_core_resource_types
    from gabriel.resource.factory import ResourceFactory
    from gabriel.resource.registry import registry
    
    # Bootstrap once at application startup
    register_core_resource_types()
    factory = ResourceFactory(registry)
    
    # Create Organization
    org = factory.create(
        "organization",
        grn=GRN.generate(org_slug, "organization"),
        org_id=org_slug,
        display_name=display_name,
        state=ResourceState.ACTIVE,
        created_by=principal_id,
        updated_by=principal_id,
    )
    
    # Create Principal (keyed by PrincipalID, not GRN)
    principal = factory.create(
        "principal",
        id=PrincipalID(org_id="acme", principal_type="user", principal_identifier="alice"),
        organization_id="acme",
        principal_type=PrincipalType.USER,
        display_name="Alice",
        status=PrincipalStatus.ACTIVE,
        capabilities={Capability.AUTHENTICATE, Capability.READ_RESOURCE},
    )
    
    Benefits:
    - Single canonical creation path
    - Uniform identifier minting
    - Consistent defaults applied by registry descriptors
    - Lifecycle management centralized
    - Future: Custom factory functions per type can inject logic


INTEGRATION POINTS:

1. Application Startup (main.py or core.py):
    from gabriel.resource.bootstrap import register_core_resource_types
    from gabriel.resource.factory import ResourceFactory
    from gabriel.resource.registry import registry
    
    # Initialize at app startup
    register_core_resource_types()
    
2. Service Layer (e.g., OrganizationService):
    from gabriel.resource.factory import ResourceFactory
    from gabriel.resource.registry import registry
    
    class OrganizationService:
        def __init__(self, repository: OrganizationRepository):
            self.repo = repository
            self.factory = ResourceFactory(registry)
        
        async def register_organization(self, display_name: str, created_by: str) -> Organization:
            org_slug = display_name.lower().replace(" ", "-")
            grn = GRN.generate(org_slug, "organization")
            
            # Create through factory (uniform path)
            org = self.factory.create(
                "organization",
                grn=grn,
                org_id=org_slug,
                display_name=display_name,
                state=ResourceState.ACTIVE,
                created_by=created_by,
                updated_by=created_by,
            )
            
            # Persist ORM representation
            orm_org = domain_to_orm(org)
            persisted = await self.repo.create(orm_org)
            return orm_to_domain(persisted)

3. Event Handlers (e.g., CreateOrganizationHandler):
    from gabriel.resource.factory import ResourceFactory
    from gabriel.resource.registry import registry
    from gabriel.resource.bootstrap import register_core_resource_types
    
    class CreateOrganizationHandler(Handler):
        def __init__(self, factory: ResourceFactory | None = None):
            register_core_resource_types()  # Idempotent
            self.factory = factory or ResourceFactory(registry)
        
        async def handle(self, command: Command) -> list[Event]:
            org_slug = command.payload["display_name"].lower().replace(" ", "-")
            grn = GRN.generate(org_id=org_slug, resource_type="organization")
            
            # Create through factory (uniform path)
            org = self.factory.create(
                "organization",
                grn=grn,
                org_id=org_slug,
                display_name=command.payload["display_name"],
                state=ResourceState.ACTIVE,
                created_by=command.principal_id,
                updated_by=command.principal_id,
            )
            
            # Emit event with created resource
            event = Event(
                type="organization_created",
                principal_id=command.principal_id,
                resource_grn=str(org.grn),
                payload={"org_id": org.org_id, "display_name": org.display_name},
            )
            return [event]

4. Future: Custom Factory Functions
    When a resource needs special construction logic, register a factory_fn:
    
    registry.register(
        ComplexResource,
        factory_fn=lambda **kwargs: ComplexResource.with_defaults(**kwargs),
        description="Complex resource with special construction",
    )
    
    # Factory automatically uses the custom factory_fn
    complex_obj = factory.create("complex_resource", ...)


KEY PRINCIPLES:

1. Single Entry Point: ResourceFactory.create() is the only way to instantiate resources
2. Registry-Driven: Descriptors centralize metadata; no if/else chains
3. Idempotent Bootstrap: register_core_resource_types() is safe to call multiple times
4. Testable: Pass mock registry or factory to tests
5. Extensible: New resource types just add a registration call
"""

# This file is documentation-only. For usage, see:
# - gabriel.resource.bootstrap (bootstrap functions)
# - gabriel.resource.factory (ResourceFactory)
# - gabriel.organization.service (OrganizationService example)
# - gabriel.events.handlers (CreateOrganizationHandler example)
