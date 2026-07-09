"""Mappers between ExternalIntegration domain and ORM."""

from gabriel.integration.models import ExternalIntegration, IntegrationType
from gabriel.integration.orm import ExternalIntegrationORM
from gabriel.resource.grn import GRN


def orm_to_domain(orm: ExternalIntegrationORM) -> ExternalIntegration:
    grn = GRN.parse(orm.grn)
    return ExternalIntegration(
        grn=grn,
        org_id=orm.org_id,
        resource_type=orm.resource_type,
        state=orm.state,
        version=orm.version,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
        created_by=orm.created_by,
        updated_by=orm.updated_by,
        metadata=orm.resource_metadata,
        labels=orm.labels,
        integration_type=IntegrationType(orm.integration_type),
        display_name=orm.display_name,
        credentials=orm.credentials,
        scopes=orm.scopes,
        is_active=orm.is_active,
    )


def domain_to_orm(domain: ExternalIntegration) -> ExternalIntegrationORM:
    return ExternalIntegrationORM(
        grn=str(domain.grn),
        org_id=domain.org_id,
        resource_type=domain.resource_type,
        state=domain.state,
        version=domain.version,
        created_at=domain.created_at,
        updated_at=domain.updated_at,
        created_by=domain.created_by,
        updated_by=domain.updated_by,
        resource_metadata=domain.metadata,
        labels=domain.labels,
        integration_type=domain.integration_type.value,
        display_name=domain.display_name,
        credentials=domain.credentials,
        scopes=domain.scopes,
        is_active=domain.is_active,
    )
