from sqlalchemy.exc import IntegrityError

from gabriel.organization.repository import OrganizationRepository
from gabriel.organization.models import Organization
from gabriel.organization.mappers import domain_to_orm, orm_to_domain
from gabriel.resource.models import ResourceState, ResourceType
from gabriel.resource.grn import GRN
from gabriel.resource.exceptions import DuplicateResourceError


class OrganizationService:
    """Business logic for Organizations.
    
    This service:
    - Accepts and returns Domain objects (Organization, not OrganizationORM)
    - Uses the repository (internal persistence layer) privately
    - Never exposes ORM models to callers
    """

    def __init__(self, repository: OrganizationRepository):
        self.repo = repository

    async def register_organization(
        self, display_name: str, created_by: str
    ) -> Organization:
        """Register a new Organization.
        
        Args:
            display_name: Human-readable organization name.
            created_by: User ID of the creator.
            
        Returns:
            Organization: The created organization domain object.
            
        Raises:
            DuplicateResourceError: If an organization with the same GRN already exists.
        """
        # 1. Build the GRN (domain object)
        org_slug = display_name.lower().replace(" ", "-")
        grn = GRN(
            org_id=org_slug,
            resource_type=ResourceType.ORGANIZATION,
            resource_id=org_slug,
        )
        grn_str = str(grn)

        # 2. Reject duplicates before hitting the DB
        try:
            await self.repo.get_by_grn(grn_str)
            raise DuplicateResourceError(
                f"Organization with GRN '{grn_str}' already exists."
            )
        except DuplicateResourceError:
            raise
        except Exception:
            pass  # ResourceNotFoundError — safe to proceed

        # 3. Build the domain object
        domain_org = Organization(
            grn=grn,
            org_id=org_slug,
            resource_type=ResourceType.ORGANIZATION,
            display_name=display_name,
            state=ResourceState.ACTIVE,
            created_by=created_by,
            updated_by=created_by,
        )

        # 4. Convert to ORM and persist (Repository is internal)
        try:
            orm_org = domain_to_orm(domain_org)
            persisted_orm = await self.repo.create(orm_org)
            # 5. Convert back to domain before returning to caller
            return orm_to_domain(persisted_orm)
        except IntegrityError as exc:
            raise DuplicateResourceError(
                f"Organization with GRN '{grn_str}' already exists."
            ) from exc

    async def get_organization(self, grn_str: str) -> Organization:
        """Retrieve an organization by its GRN string.
        
        Args:
            grn_str: The GRN as a string (e.g., "grn://acme/organization/acme@1").
            
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