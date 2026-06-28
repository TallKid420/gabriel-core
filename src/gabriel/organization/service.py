from sqlalchemy.exc import IntegrityError

from gabriel.organization.repository import OrganizationRepository
from gabriel.organization.orm import OrganizationORM
from gabriel.resource.models import ResourceState, ResourceType
from gabriel.resource.grn import GRN
from gabriel.resource.exceptions import DuplicateResourceError


class OrganizationService:
    def __init__(self, repository: OrganizationRepository):
        self.repo = repository

    async def register_organization(self, display_name: str, created_by: str) -> OrganizationORM:
        # 1. Create the GRN
        org_slug = display_name.lower().replace(" ", "-")
        grn = GRN(org_id=org_slug, resource_type=ResourceType.ORGANIZATION, resource_id=org_slug)
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

        # 3. Map to ORM
        new_org = OrganizationORM(
            grn=grn_str,
            org_id=org_slug,
            resource_type=ResourceType.ORGANIZATION,
            display_name=display_name,
            state=ResourceState.ACTIVE,
            created_by=created_by,
            updated_by=created_by,
        )

        # 4. Persist — IntegrityError is a last-resort safety net
        try:
            return await self.repo.create(new_org)
        except IntegrityError as exc:
            raise DuplicateResourceError(
                f"Organization with GRN '{grn_str}' already exists."
            ) from exc