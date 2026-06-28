from gabriel.resource.models import ResourceState
from gabriel.resource.exceptions import InvalidLifecycleTransitionError

# Define which transitions are permitted
ALLOWED_TRANSITIONS: dict[ResourceState, set[ResourceState]] = {
    ResourceState.DRAFT:      {ResourceState.ACTIVE, ResourceState.DELETED},
    ResourceState.ACTIVE:     {ResourceState.SUSPENDED, ResourceState.DEPRECATED, ResourceState.DELETED},
    ResourceState.SUSPENDED:  {ResourceState.ACTIVE, ResourceState.DELETED},
    ResourceState.DEPRECATED: {ResourceState.DELETED},
    ResourceState.DELETED:    set(),
}

class LifecycleManager:

    @staticmethod
    def validate_transition(current: ResourceState, target: ResourceState) -> None:
        # TODO: raise InvalidLifecycleTransitionError if transition is not in ALLOWED_TRANSITIONS
        if target not in ALLOWED_TRANSITIONS.get(current, set()):
            raise InvalidLifecycleTransitionError(f"Invalid transition from {current} to {target}")
        else:
            return None

    @staticmethod
    def transition(resource, target: ResourceState, updated_by: str):
        """validate then return resource.with_state(target, updated_by)"""
        LifecycleManager.validate_transition(resource.state, target)
        return resource.with_state(target, updated_by)