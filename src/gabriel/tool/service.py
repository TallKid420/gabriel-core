from sqlalchemy.exc import IntegrityError

from gabriel.tool.repository import ToolRepository
from gabriel.tool.models import Tool
from gabriel.tool.mappers import domain_to_orm, orm_to_domain
from gabriel.resource.models import ResourceState
from gabriel.resource.grn import GRN
from gabriel.resource.exceptions import DuplicateResourceError
from gabriel.resource.factory import ResourceFactory
from gabriel.resource.registry import registry
from gabriel.resource.bootstrap import register_core_resource_types
from gabriel.events.repository import EventRepository
from gabriel.events.event import Event

class ToolService:
    """Business logic for Tools.
    
    This service:
    - Accepts and returns Domain objects (Tool, not ToolORM)
    - Uses the repository (internal persistence layer) privately
    - Never exposes ORM models to callers
    - Emits events transactionally (ADR-017 outbox pattern)
    """

    def __init__(self, repository: ToolRepository, event_repo: EventRepository | None = None):
        register_core_resource_types()
        self.repo = repository
        self.event_repo = event_repo
        self.factory = ResourceFactory(registry)