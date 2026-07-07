"""Policy lifecycle service."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from gabriel.events.event import Event
from gabriel.events.repository import EventRepository
from gabriel.policy.mappers import domain_to_orm, orm_to_domain
from gabriel.policy.models import Policy, PolicyStatement
from gabriel.policy.repository import PolicyRepository
from gabriel.resource.bootstrap import register_core_resource_types
from gabriel.resource.exceptions import DuplicateResourceError
from gabriel.resource.factory import ResourceFactory
from gabriel.resource.grn import GRN
from gabriel.resource.models import ResourceState
from gabriel.resource.registry import registry


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PolicyService:
    """Business logic for policies."""

    def __init__(self, repository: PolicyRepository, event_repo: EventRepository | None = None):
        register_core_resource_types()
        self.repo = repository
        self.event_repo = event_repo
        self.factory = ResourceFactory(registry)

    async def create_policy(
        self,
        org_id: str,
        created_by: str,
        statements: list[PolicyStatement],
        *,
        policy_grn: str | None = None,
        metadata: dict | None = None,
        labels: dict[str, str] | None = None,
        correlation_id: str | None = None,
    ) -> Policy:
        grn = GRN.parse(policy_grn) if policy_grn else GRN.generate(org_id, "policy")
        grn_str = str(grn)

        domain_policy = self.factory.create(
            "policy",
            grn=grn,
            org_id=org_id,
            created_by=created_by,
            statements=statements,
            labels=labels or {},
            metadata=metadata or {},
        )

        try:
            persisted_orm = await self.repo.create(domain_to_orm(domain_policy))
            if self.event_repo is not None:
                await self.event_repo.append(
                    Event(
                        type="resource_created",
                        principal_id=created_by,
                        organization_id=org_id,
                        resource_grn=grn_str,
                        correlation_id=correlation_id,
                        payload={
                            "resource_type": "policy",
                            "grn": grn_str,
                        },
                        metadata={
                            "service": "PolicyService",
                            "operation": "create_policy",
                        },
                    )
                )
                await self.repo.session.commit()
            return orm_to_domain(persisted_orm)
        except IntegrityError as exc:
            raise DuplicateResourceError(f"Policy with GRN '{grn_str}' already exists.") from exc

    async def get_policy(self, grn_str: str) -> Policy:
        orm_policy = await self.repo.get_by_grn(grn_str)
        return orm_to_domain(orm_policy)

    async def list_policies(self, org_id: str | None = None) -> list[Policy]:
        orm_policies = await self.repo.list_for_org(org_id) if org_id else await self.repo.list_all()
        return [orm_to_domain(policy) for policy in orm_policies]

    async def update_policy(
        self,
        grn_str: str,
        updated_by: str,
        statements: list[PolicyStatement],
        *,
        correlation_id: str | None = None,
    ) -> Policy:
        existing = orm_to_domain(await self.repo.get_by_grn(grn_str))
        updated = existing.model_copy(
            update={
                "statements": statements,
                "updated_by": updated_by,
                "updated_at": utcnow(),
                "version": existing.version + 1,
                "state": ResourceState.ACTIVE,
            }
        )

        persisted = await self.repo.update(domain_to_orm(updated))
        if self.event_repo is not None:
            await self.event_repo.append(
                Event(
                    type="resource_updated",
                    principal_id=updated_by,
                    organization_id=existing.org_id,
                    resource_grn=grn_str,
                    correlation_id=correlation_id,
                    payload={
                        "resource_type": "policy",
                        "grn": grn_str,
                    },
                    metadata={
                        "service": "PolicyService",
                        "operation": "update_policy",
                    },
                )
            )
            await self.repo.session.commit()
        return orm_to_domain(persisted)

    async def delete_policy(
        self,
        grn_str: str,
        deleted_by: str,
        *,
        correlation_id: str | None = None,
    ) -> None:
        existing = orm_to_domain(await self.repo.get_by_grn(grn_str))
        await self.repo.delete(grn_str)
        if self.event_repo is not None:
            await self.event_repo.append(
                Event(
                    type="resource_deleted",
                    principal_id=deleted_by,
                    organization_id=existing.org_id,
                    resource_grn=grn_str,
                    correlation_id=correlation_id,
                    payload={
                        "resource_type": "policy",
                        "grn": grn_str,
                    },
                    metadata={
                        "service": "PolicyService",
                        "operation": "delete_policy",
                    },
                )
            )
            await self.repo.session.commit()
