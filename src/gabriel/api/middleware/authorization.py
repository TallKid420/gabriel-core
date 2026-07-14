from __future__ import annotations

import base64
import inspect
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from gabriel.api.auth import AuthenticationError, authenticate_token, extract_bearer_token
from gabriel.events.audit import PeelEvaluationEvent
from gabriel.policy.engine import Effect
from gabriel.runtime.context import ExecutionContext


_REQUEST_LOG_PATH_ENV = "GABRIEL_REQUEST_LOG_PATH"
_DEFAULT_REQUEST_LOG_PATH = Path(".gabriel") / "requests.log"


def _build_request_logger() -> logging.Logger:
    logger = logging.getLogger("gabriel.api.requests")
    if logger.handlers:
        return logger

    configured_path = os.getenv(_REQUEST_LOG_PATH_ENV)
    log_path = Path(configured_path) if configured_path else _DEFAULT_REQUEST_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(log_path, encoding="utf-8")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


_REQUEST_LOGGER = _build_request_logger()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _encode_request_body(body: bytes) -> tuple[str, str]:
    try:
        return body.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return base64.b64encode(body).decode("ascii"), "base64"


async def _capture_request_body(request: Request) -> bytes:
    # Starlette's BaseHTTPMiddleware wraps the request in a ``_CachedRequest``
    # that replays the consumed body to the downstream app automatically, so
    # reading it here is safe. Do NOT monkeypatch ``request._receive`` to
    # re-emit ``http.request`` frames: streaming endpoints (SSE) listen for
    # ``http.disconnect`` after the body is consumed, and a replayed body
    # frame crashes the response cycle.
    return await request.body()


async def _log_incoming_request(request: Request, request_id: str) -> None:
    if request.method in ("POST", "PUT", "PATCH"):
        body = await _capture_request_body(request)
    else:
        body = b""
    body_text, body_encoding = _encode_request_body(body)

    payload = {
        "timestamp": _utcnow().isoformat(),
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "query_string": request.url.query,
        "client": request.client.host if request.client else None,
        "headers": dict(request.headers),
        "body": body_text,
        "body_encoding": body_encoding,
    }
    _REQUEST_LOGGER.info(json.dumps(payload, ensure_ascii=True))


_DOMAIN_BY_PREFIX = {
    "resources": "resource",
    "agents": "agent",
    "memory": "memory",
    "documents": "document",
    "events": "resource",
    "executions": "agent",
    "organizations": "organization",
    "identities": "identity",
    "users": "user",
    "conversations": "conversation",
    "notifications": "notification",
    "gateway": "gateway",
}

_VERB_BY_METHOD = {
    "GET": "read",
    "HEAD": "read",
    "POST": "create",
    "PUT": "update",
    "PATCH": "update",
    "DELETE": "delete",
}

_PUBLIC_PATHS = {"/docs", "/openapi.json", "/redoc"}
# Agent-specification authoring/config endpoints are consumed by the desktop
# BFF over HTTP (Phase 4 wiring). They carry no principal-scoped data and are
# allowlisted so the gateway can drive template/spec workflows.
_PUBLIC_PREFIXES = ("/health", "/auth", "/api/v1/auth", "/api/v1/agent-specs")


def _normalize_api_path(path: str) -> str:
    if path.startswith("/api/v1/"):
        return path[len("/api/v1"):]
    if path == "/api/v1":
        return "/"
    return path


def _is_public_request_path(request: Request) -> bool:
    if request.method == "OPTIONS":
        return True

    path = request.url.path
    if path in _PUBLIC_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)


def _derive_action(request: Request) -> str | None:
    path = _normalize_api_path(request.url.path).strip("/")
    if not path:
        return None

    segments = path.split("/")
    domain = _DOMAIN_BY_PREFIX.get(segments[0])
    if domain is None:
        return None

    verb = _VERB_BY_METHOD.get(request.method.upper(), "read")
    if domain == "agent" and request.method.upper() == "POST" and segments[-1] == "execute":
        verb = "execute"
    return f"{domain}:{verb}"


def _extract_resource_identifier(request: Request) -> str:
    path = _normalize_api_path(request.url.path).strip("/")
    if not path:
        return ""

    segments = path.split("/")
    if len(segments) <= 1:
        return ""

    candidate = "/".join(segments[1:])
    for suffix in ("/execute", "/disable", "/enable"):
        if candidate.endswith(suffix):
            candidate = candidate[: -len(suffix)]
            break
    return candidate


def _parse_correlation_id(raw: str | None) -> UUID:
    if not raw:
        return uuid4()
    try:
        return UUID(raw)
    except ValueError:
        return uuid4()


async def _append_audit_event(request: Request, event: PeelEvaluationEvent) -> None:
    gateway_state = getattr(request.app.state, "gateway_state", None)
    if gateway_state is None:
        return

    dispatcher = getattr(gateway_state, "dispatcher", None)
    if dispatcher is not None and hasattr(dispatcher, "record_event"):
        await dispatcher.record_event(event)
        return

    event_store = getattr(gateway_state, "event_store", None)
    if event_store is None:
        return

    append_result = event_store.append(event)
    if inspect.isawaitable(append_result):
        await append_result


def _build_peel_evaluation_event(
    request: Request,
    context: ExecutionContext,
    action: str,
    resource_grn: str,
    decision: Effect,
) -> PeelEvaluationEvent:
    return PeelEvaluationEvent(
        principal_id=str(context.principal.id),
        organization_id=context.organization,
        resource_grn=resource_grn or None,
        correlation_id=str(context.correlation_id),
        payload={
            "decision": decision.value,
            "action": action,
            "resource_grn": resource_grn,
            "method": request.method,
            "path": request.url.path,
        },
        metadata={
            "request_id": getattr(request.state, "request_id", None),
            "source": "api.middleware.authorization",
        },
    )


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        request_id = request.headers.get("x-request-id", str(uuid4()))
        request.state.request_id = request_id
        request.state.execution_context = None

        await _log_incoming_request(request, request_id)

        try:
            identity_service = getattr(request.app.state, "identity_service", None)
            if identity_service is None:
                raise AuthenticationError("Identity service is not initialized")

            token = extract_bearer_token(request.headers.get("authorization"))
            if token is None:
                cookie_name = identity_service.settings.session_cookie_name
                token = request.cookies.get(cookie_name)

            auth_result = await authenticate_token(identity_service, token)

            correlation_id = _parse_correlation_id(request.headers.get("x-correlation-id"))
            request.state.execution_context = ExecutionContext(
                execution_id=uuid4(),
                principal=auth_result.principal,
                organization=auth_result.principal.organization_id,
                correlation_id=correlation_id,
                causation_id=None,
                session_id=None,
                resource=None,
                started_at=_utcnow(),
                capabilities=frozenset(
                    cap.value for cap in auth_result.principal.capabilities
                ),
                metadata={
                    "request_id": request_id,
                    "path": request.url.path,
                    "method": request.method,
                },
            )
        except AuthenticationError:
            if _is_public_request_path(request):
                return await call_next(request)
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized", "request_id": request_id},
            )

        peel = getattr(request.app.state, "peel", None)
        if peel is not None and not _is_public_request_path(request):
            action = _derive_action(request)
            if action is not None:
                resource_grn = _extract_resource_identifier(request)
                decision = await peel.evaluate(
                    request.state.execution_context,
                    action,
                    resource_grn,
                )
                await _append_audit_event(
                    request,
                    _build_peel_evaluation_event(
                        request,
                        request.state.execution_context,
                        action,
                        resource_grn,
                        decision,
                    ),
                )
                if decision == Effect.DENY:
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Forbidden", "request_id": request_id},
                    )

        return await call_next(request)


__all__ = [
    "PeelEvaluationEvent",
    "RequestContextMiddleware",
    "_derive_action",
    "_extract_resource_identifier",
    "_is_public_request_path",
]