from pydantic import BaseModel, Field

class AgentSpecification(BaseModel):
    name: str
    description: str = ""
    runtime: str
    model: str
    system_prompt: str
    capabilites: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    memory_layers: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)