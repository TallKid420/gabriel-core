import pytest
from gabriel.resource.lifecycle import LifecycleManager
from gabriel.resource.models import ResourceState
from gabriel.resource.exceptions import InvalidLifecycleTransitionError

def test_draft_to_active_allowed():
    LifecycleManager.validate_transition(ResourceState.DRAFT, ResourceState.ACTIVE)

def test_draft_to_suspended_raises():
    with pytest.raises(InvalidLifecycleTransitionError):
        LifecycleManager.validate_transition(ResourceState.DRAFT, ResourceState.SUSPENDED)

def test_deleted_is_terminal():
    with pytest.raises(InvalidLifecycleTransitionError):
        LifecycleManager.validate_transition(ResourceState.DELETED, ResourceState.ACTIVE)