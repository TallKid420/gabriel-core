"""ToolExecutor — secure dispatch engine for Gabriel tools.

The executor is the single entry-point for all tool invocations.  Callers
(agents, API handlers) must never call tool functions directly.

Invocation pipeline
-------------------
1. Resolve ``Tool`` resource from GRN via :class:`ToolService`.
2. Validate input arguments against ``tool.input_schema`` (JSON Schema).
3. PEEL check — ``tool:invoke`` action gated by :class:`PEEL`.
4. Resolve callable from :class:`~gabriel.tool.registry.FunctionRegistry`.
5. Dispatch: ``await fn(**kwargs)``.
6. Validate output against ``tool.output_schema``.
7. Emit :class:`ToolInvokedEvent` to the event repository (ADR-003).

ADR compliance
--------------
- ADR-003 (Events): ``ToolInvokedEvent`` emitted on every successful invocation.
- ADR-019 (PEEL): Every invocation cleared by PEEL before dispatch.
- ADR-016 (Tool Registry): Tool resource resolved from GRN; callable from
  FunctionRegistry.
- ADR-024 (Schema Validation): Input AND output validated against JSON Schema.
"""

from __future__ import annotations

import time
from typing import Any

import jsonschema

from gabriel.events.event import Event
from gabriel.events.repository import EventRepository
from gabriel.logging_config import get_logger
from gabriel.policy.exceptions import UnauthorizedError
from gabriel.policy.peel import PEEL
from gabriel.runtime.context import ExecutionContext
from gabriel.tool.models import SafetyLevel, Tool
from gabriel.tool.registry import FunctionRegistry
from gabriel.tool.service import ToolService
from gabriel.tool.exceptions import (
    ConfirmationRequiredError,
    SchemaValidationError,
    ToolInvocationError,
    ToolNotFoundError,
)

logger = get_logger(__name__)

class ToolExecutor:
    """Secure dispatch engine for Gabriel tools.

    Args:
        tool_service:   Used to resolve :class:`Tool` resources by GRN.
        fn_registry:    In-process callable registry (pure / file tools).
        peel:           Policy Enforcement & Evaluation Layer.
        event_repo:     Optional event repository for audit emission.
    """

    def __init__(
        self,
        tool_service: ToolService,
        fn_registry: FunctionRegistry,
        peel: PEEL,
        event_repo: EventRepository | None = None,
    ) -> None:
        self.tool_service = tool_service
        self.fn_registry = fn_registry
        self.peel = peel
        self.event_repo = event_repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def invoke(
        self,
        context: ExecutionContext,
        tool_grn: str,
        arguments: dict[str, Any],
        *,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        """Invoke a tool and return its output.

        Args:
            context:   The caller's execution context (principal + capabilities).
            tool_grn:  GRN of the Tool resource to invoke.
            arguments: Keyword arguments passed to the tool function.
            confirmed: Must be ``True`` for ``REQUIRES_CONFIRMATION`` tools.
                       If ``False``, :class:`ConfirmationRequiredError` is raised
                       so the caller can prompt the user.

        Returns:
            The tool's output dict (validated against ``output_schema``).

        Raises:
            ToolNotFoundError:         GRN not found or no callable registered.
            SchemaValidationError:     Input/output schema mismatch.
            ConfirmationRequiredError: Tool requires human approval.
            UnauthorizedError:         PEEL denied the invocation.
            ToolInvocationError:       Any other execution failure.
        """
        # 1. Resolve Tool resource
        tool = await self._resolve_tool(tool_grn)

        # 2. Validate inputs
        self._validate_schema(arguments, tool.input_schema, "input", tool.name)

        # 3. PEEL check
        await self.peel.authorize(context, "tool:invoke", tool_grn)

        # 4. Confirmation gate
        if tool.safety_level == SafetyLevel.REQUIRES_CONFIRMATION and not confirmed:
            raise ConfirmationRequiredError(
                f"Tool '{tool.name}' requires explicit confirmation before it may "
                "be invoked.  Re-invoke with confirmed=True after user approval."
            )

        # 5. Resolve callable
        fn = self._resolve_callable(tool)

        # 6. Dispatch
        started_at = time.monotonic()
        try:
            result = await fn(**arguments)
        except Exception as exc:
            logger.exception("Tool '%s' raised during invocation", tool.name)
            await self._emit_event(context, tool, success=False, error=str(exc))
            raise ToolInvocationError(
                f"Tool '{tool.name}' failed: {exc}"
            ) from exc
        elapsed_ms = int((time.monotonic() - started_at) * 1000)

        # 7. Validate output
        self._validate_schema(result, tool.output_schema, "output", tool.name)

        # 8. Emit audit event
        await self._emit_event(
            context,
            tool,
            success=True,
            elapsed_ms=elapsed_ms,
        )

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _resolve_tool(self, grn: str) -> Tool:
        try:
            return await self.tool_service.get_tool(grn)
        except Exception as exc:
            raise ToolNotFoundError(
                f"Cannot resolve Tool resource for GRN '{grn}': {exc}"
            ) from exc

    def _resolve_callable(self, tool: Tool):  # type: ignore[return]
        fn = self.fn_registry.get(tool.runtime_binding)
        if fn is None:
            raise ToolNotFoundError(
                f"No callable registered for runtime_binding "
                f"'{tool.runtime_binding}' (tool: '{tool.name}'). "
                "Import the tool library package to register it."
            )
        return fn

    @staticmethod
    def _validate_schema(
        data: dict[str, Any],
        schema: dict[str, Any],
        direction: str,
        tool_name: str,
    ) -> None:
        """Validate *data* against *schema*.  Raises :class:`SchemaValidationError`."""
        if not schema:
            # Empty schema = no validation (opt-out)
            return
        try:
            jsonschema.validate(instance=data, schema=schema)
        except jsonschema.ValidationError as exc:
            raise SchemaValidationError(
                f"Tool '{tool_name}' {direction} schema validation failed: "
                f"{exc.message}"
            ) from exc

    async def _emit_event(
        self,
        context: ExecutionContext,
        tool: Tool,
        *,
        success: bool,
        elapsed_ms: int = 0,
        error: str | None = None,
    ) -> None:
        """Emit a ``tool_invoked`` audit event (ADR-003)."""
        if self.event_repo is None:
            return
        payload: dict[str, Any] = {
            "tool_grn": str(tool.grn),
            "tool_name": tool.name,
            "runtime_binding": tool.runtime_binding,
            "safety_level": tool.safety_level.value,
            "success": success,
            "elapsed_ms": elapsed_ms,
        }
        if error:
            payload["error"] = error

        try:
            await self.event_repo.append(
                Event(
                    type="tool_invoked",
                    principal_id=str(context.principal.id),
                    organization_id=context.organization,
                    resource_grn=str(tool.grn),
                    correlation_id=str(context.correlation_id),
                    payload=payload,
                    metadata={
                        "service": "ToolExecutor",
                        "operation": "invoke",
                        "session_id": (
                            str(context.session_id) if context.session_id else None
                        ),
                    },
                )
            )
        except Exception:
            # Event emission must NEVER block tool results from reaching the caller.
            logger.exception(
                "ToolExecutor: failed to emit tool_invoked event for '%s'",
                tool.name,
            )
