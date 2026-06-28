import pytest

from gabriel.runtime.exceptions import DuplicateRuntimeError, RuntimeNotFoundError
from gabriel.runtime.mock_runtime import MockRuntime
from gabriel.runtime.registry import RuntimeRegistry


def test_runtime_registration() -> None:
    registry = RuntimeRegistry()
    runtime = MockRuntime()

    registry.register(runtime)

    assert registry.get("mock") is runtime


def test_duplicate_runtime() -> None:
    registry = RuntimeRegistry()
    registry.register(MockRuntime())

    with pytest.raises(DuplicateRuntimeError):
        registry.register(MockRuntime())


def test_unknown_runtime() -> None:
    registry = RuntimeRegistry()

    with pytest.raises(RuntimeNotFoundError):
        registry.get("does-not-exist")
