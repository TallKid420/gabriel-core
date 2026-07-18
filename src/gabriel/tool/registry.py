"""FunctionRegistry — in-process callable registry for the ToolExecutor.

Design
------
The FunctionRegistry maps a ``runtime_binding`` string (e.g. ``"math.calculate"``)
to a plain Python coroutine (async function).  It is the *only* lookup mechanism
the ToolExecutor uses to dispatch SAFE and FILE tools.

Integration tools (email, calendar) resolve their callables through a separate
IntegrationRegistry that requires org-scoped credentials — see
:mod:`gabriel.tool.integration_registry`.

Registration
------------
Tool libraries self-register at import time by calling
:func:`function_registry.register`.  Callers only need to import the library
package to make its tools available:

    >>> import gabriel.tool.library.math  # registers math.* tools
    >>> fn = function_registry.get("math.calculate")

ADR compliance
--------------
- ADR-016 (Tool Registry): All tool callables pass through a registry before
  the executor dispatches them.
- ADR-003 (Events): Registration is side-effect-only; events are emitted by
  the ToolExecutor, not here.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from gabriel.logging_config import get_logger

logger = get_logger(__name__)

# Callable type alias: any async function that accepts keyword arguments and
# returns a JSON-serialisable dict (or raises on error).
ToolFn = Callable[..., Coroutine[Any, Any, dict[str, Any]]]


class FunctionRegistry:
    """Thread-safe, process-local registry of tool callables.

    Keys are dot-path strings that match the ``runtime_binding`` field of a
    :class:`~gabriel.tool.models.Tool` resource.

    Examples::

        math.calculate
        text.hash_text
        file.find_file
    """

    def __init__(self) -> None:
        self._registry: dict[str, ToolFn] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, binding: str, fn: ToolFn) -> None:
        """Register *fn* under *binding*.

        Args:
            binding: Dot-path key, e.g. ``"math.calculate"``.
            fn:      Async callable.  Must accept ``**kwargs`` and return a
                     ``dict``.

        Raises:
            ValueError: If *binding* is already registered (prevents silent
                        overwrites during startup).
        """

        if binding in self._registry:
            raise ValueError(
                f"FunctionRegistry: binding '{binding}' is already registered"
                "Import order conflict or duplicate registration."
            )
        self._registry[binding] = fn
        logger.debug("FunctionRegistry: registered '%s'", binding)

    def register_many(self, bindings: dict[str, ToolFn]) -> None:
        """Register multiple callables at once.

        Useful for library ``__init__.py`` modules that expose a mapping.
        """
        for binding, fn in bindings.items():
            self.register(binding, fn)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, binding: str) -> ToolFn | None:
        """Return the callable for *binding*, or ``None`` if not registered."""
        return self._registry.get(binding)

    def require(self, binding: str) -> ToolFn:
        """Return the callable for *binding*.

        Raises:
            KeyError: If *binding* is not registered.
        """
        fn = self._registry.get(binding)
        if fn is None:
            raise KeyError(
                f"FunctionRegistry: no callable registered for '{binding}'. "
                "Did you forget to import the tool library?"
            )
        return fn

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_bindings(self) -> list[str]:
        """Return a sorted list of all registered binding keys."""
        return sorted(self._registry)

    def is_registered(self, binding: str) -> bool:
        return binding in self._registry

    def __len__(self) -> int:
        return len(self._registry)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<FunctionRegistry bindings={len(self._registry)}>"


# ---------------------------------------------------------------------------
# Module-level singleton — import this wherever you need tool dispatch.
# ---------------------------------------------------------------------------
function_registry: FunctionRegistry = FunctionRegistry()
