from sqlalchemy.exc import IntegrityError

from gabriel.organization.repository import OrganizationRepository
from gabriel.organization.models import Organization
from gabriel.organization.mappers import domain_to_orm, orm_to_domain
from gabriel.resource.models import ResourceState
from gabriel.resource.grn import GRN
from gabriel.resource.exceptions import DuplicateResourceError
from gabriel.resource.factory import ResourceFactory
from gabriel.resource.registry import registry
from gabriel.resource.bootstrap import register_core_resource_types
from gabriel.events.repository import EventRepository
from gabriel.events.event import Event


class OrganizationService:
    """Business logic for Organizations.
    
    This service:
    - Accepts and returns Domain objects (Organization, not OrganizationORM)
    - Uses the repository (internal persistence layer) privately
    - Never exposes ORM models to callers
    - Emits events transactionally (ADR-017 outbox pattern)
    """

    def __init__(self, repository: OrganizationRepository, event_repo: EventRepository | None = None):
        register_core_resource_types()
        self.repo = repository
        self.event_repo = event_repo
        self.factory = ResourceFactory(registry)

    async def register_organization(
        self, display_name: str, created_by: str, correlation_id: str | None = None
    ) -> Organization:
        """Register a new Organization.
        
        Implements transactional outbox pattern (ADR-017):
        - Inserts organization row
        - Appends resource_created event
        - Both committed together
        
        Args:
            display_name: Human-readable organization name.
            created_by: User ID of the creator.
            correlation_id: Optional trace ID for this operation.
            
        Returns:
            Organization: The created organization domain object.
            
        Raises:
            DuplicateResourceError: If an organization with the same GRN already exists.
        """
        # 1. Derive org identity and enforce uniqueness on org_id
        org_slug = display_name.lower().replace(" ", "-")

        existing_orgs = await self.repo.list_all()
        if any(existing.org_id == org_slug for existing in existing_orgs):
            raise DuplicateResourceError(
                f"Organization with org_id '{org_slug}' already exists."
            )

        # 2. Build the GRN via factory (Step 1 - remint GRN via factory)
        grn = GRN.generate(org_slug, "organization")
        grn_str = str(grn)

        # 3. Build the domain object via factory
        domain_org = self.factory.create(
            "organization",
            grn=grn,
            org_id=org_slug,
            display_name=display_name,
            state=ResourceState.ACTIVE,
            created_by=created_by,
            updated_by=created_by,
        )

        # 4. Convert to ORM and persist (Repository is internal)
        try:
            orm_org = domain_to_orm(domain_org)
            persisted_orm = await self.repo.create(orm_org)
            
            # 5. Emit resource_created event transactionally (Step 3 + Step 4)
            # This is the outbox pattern: event appended in same transaction as resource
            if self.event_repo is not None:
                event = Event(
                    type="resource_created",
                    principal_id=created_by,
                    organization_id=org_slug,
                    resource_grn=grn_str,
                    correlation_id=correlation_id,
                    payload={
                        "resource_type": "organization",
                        "org_id": org_slug,
                        "display_name": display_name,
                        "grn": grn_str,
                    },
                    metadata={
                        "service": "OrganizationService",
                        "operation": "register_organization",
                    },
                )
                # Append event in the same transaction (no explicit commit)
                await self.event_repo.append(event)
                # Commit both resource and event together
                await self.repo.session.commit()
            
            # 6. Convert back to domain before returning to caller
            return orm_to_domain(persisted_orm)
        except IntegrityError as exc:
            raise DuplicateResourceError(
                f"Organization with GRN '{grn_str}' already exists."
            ) from exc

    async def get_organization(self, grn_str: str) -> Organization:
        """Retrieve an organization by its GRN string.
        
        Args:
            grn_str: The GRN as a string (e.g., "grn:org:organization:acme@1").
            
        Returns:
            Organization: The organization domain object.
            
        Raises:
            ResourceNotFoundError: If the organization does not exist.
        """
        orm_org = await self.repo.get_by_grn(grn_str)
        return orm_to_domain(orm_org)

    async def list_organizations(self) -> list[Organization]:
        """List all organizations.
        
        Returns:
            list[Organization]: All organizations as domain objects.
        """
        orm_orgs = await self.repo.list_all()
        return [orm_to_domain(org) for org in orm_orgs]