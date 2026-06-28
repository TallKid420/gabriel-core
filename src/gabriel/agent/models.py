from gabriel.resource.models import Resource
from gabriel.agent.specification import AgentSpecification

class Agent(Resource):
    specification: AgentSpecification
    enabled: bool = True