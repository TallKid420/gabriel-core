"""Agent subsystem exceptions."""


class AgentError(Exception):
	"""Base exception for agent subsystem errors."""


class AgentValidationError(AgentError):
	"""Raised when an AgentSpecification is invalid."""


class AgentDeploymentError(AgentError):
	"""Raised when agent deployment fails."""
