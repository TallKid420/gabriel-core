from gabriel.agent.specification import AgentSpecification
from gabriel.agent.models import Agent

class AgentValidator:
    def validate(
            self,
            specification: AgentSpecification,
    ):
        """
        TODO:Before an Agent is accepted the following must be validated
            - Runtime exists
            - Tools exist
            - requested capabilities exist
            - trigger definitions are valid
            - memory layers exist
            - model exists
        """
        raise NotImplementedError
    
class AgentDeploymentService:
    async def deploy(
        self,
        specification: AgentSpecification
    ) -> Agent:
        """
        TODO: Implament Code
        """

        # Validate
        AgentValidator.validate(specification=specification) # FIXME

        # TODO: Create agent resource

        # TODO: Register triggers

        # NOTE: No runtime execution yet.