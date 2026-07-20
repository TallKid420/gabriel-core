"""Mappers between Domain (Tool) and Persistence (ToolORM)."""

from gabriel.resource.grn import GRN
from gabriel.tool.models import ExecutionRuntime, SafetyLevel, Tool, ToolCategory
from gabriel.tool.orm import ToolORM


def orm_to_domain(orm: ToolORM) -> Tool:
    """Convert a :class:`ToolORM` row to a :class:`Tool` domain object."""
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
        category=ToolCategory(orm.category),
        parameters=orm.parameters,
        safety_level=SafetyLevel(orm.safety_level),
        runtime_binding=orm.runtime_binding,
        execution_runtime=ExecutionRuntime(orm.execution_runtime or "local"),
        enabled=orm.enabled if orm.enabled is not None else True,
        configuration=orm.configuration or {},
    )


def domain_to_orm(domain: Tool) -> ToolORM:
    """Convert a :class:`Tool` domain object to a :class:`ToolORM` row."""
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
        # Store enum as its raw value so DB stays stable across renames
        category=domain.category.value,
        parameters=domain.parameters,
        safety_level=domain.safety_level.value,
        runtime_binding=domain.runtime_binding,
        execution_runtime=domain.execution_runtime.value,
        enabled=domain.enabled,
        configuration=domain.configuration,
    )
