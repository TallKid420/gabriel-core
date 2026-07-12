"""Gabriel agent specification and deployment exports."""

from gabriel.agent.capabilities import (
    AGENT_TO_RUNTIME_CAPABILITY,
    AgentCapabilities,
    AgentCapability,
    to_runtime_capabilities,
)
from gabriel.agent.deployment import AgentDeploymentService
from gabriel.agent.exceptions import AgentDeploymentError, AgentError, AgentValidationError
from gabriel.agent.grn_bindings import (
    ToolBinding,
    is_tool_grn,
    parse_tool_grn,
    resolve_tools,
    tool_grn,
    tool_name,
)
from gabriel.agent.mappers import domain_to_orm, orm_to_domain
from gabriel.agent.memory import MemoryRequirements
from gabriel.agent.models import Agent
from gabriel.agent.orm import AgentORM
from gabriel.agent.repository import AgentRepository
from gabriel.agent.runtime_config import RuntimeConfiguration
from gabriel.agent.service import AgentService
from gabriel.agent.specification import AgentSpecification
from gabriel.agent.store import AgentSpecificationStore, SpecificationNotFoundError
from gabriel.agent.templates import (
    AGENT_TEMPLATES,
    AgentTemplate,
    build_specification,
    get_template,
    list_templates,
    template_vocabulary,
)
from gabriel.agent.triggers import Trigger
from gabriel.agent.validator import AgentValidator

__all__ = [
    "Agent",
    "AgentORM",
    "AgentCapabilities",
    "AgentCapability",
    "AGENT_TO_RUNTIME_CAPABILITY",
    "to_runtime_capabilities",
    "AgentSpecification",
    "AgentDeploymentService",
    "AgentValidator",
    "AgentRepository",
    "AgentService",
    "domain_to_orm",
    "orm_to_domain",
    "MemoryRequirements",
    "RuntimeConfiguration",
    "Trigger",
    "AgentError",
    "AgentValidationError",
    "AgentDeploymentError",
    # GRN tool bindings
    "ToolBinding",
    "tool_grn",
    "tool_name",
    "is_tool_grn",
    "parse_tool_grn",
    "resolve_tools",
    # Templates
    "AgentTemplate",
    "AGENT_TEMPLATES",
    "build_specification",
    "get_template",
    "list_templates",
    "template_vocabulary",
    # Persistence
    "AgentSpecificationStore",
    "SpecificationNotFoundError",
]
