"""Mappers between Domain (Tool) and Persistence (ToolORM)."""

from gabriel.resource.grn import GRN
from gabriel.tool.models import Tool
from gabriel.tool.orm import ToolORM

def orm_to_domain(orm: ToolORM) -> Tool:
    grn = GRN.parse(orm.grn)

    return Tool(
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
        name=orm.name,
        description=orm.description,
        category=orm.category,
        input_schema=orm.input_schema,
        output_schema=orm.output_schema,
        safety_level=orm.safety_level,
        required_capabilities=orm.required_capabilities,
    )

def domain_to_orm(domain: Tool) -> ToolORM:
    return ToolORM(
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
        name=domain.name,
        description=domain.description,
        category=domain.category,
        input_schema=domain.input_schema,
        output_schema=domain.output_schema,
        safety_level=domain.safety_level,
        required_capabilities=domain.required_capabilities,
    )