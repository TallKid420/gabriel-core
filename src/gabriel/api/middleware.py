from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from gabriel.api.auth import (
    AuthenticationError,
    authenticate_token,
    extract_bearer_token,
)
from gabriel.policy.exceptions import UnauthorizedError
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


def _encode_request_body(body: bytes) -> tuple[str, str]:
        try:
                return body.decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
                return base64.b64encode(body).decode("ascii"), "base64"


async def _capture_request_body(request: Request) -> bytes:
        body = await request.body()

        async def receive() -> dict[str, object]:
                return {"type": "http.request", "body": body, "more_body": False}

        # Replay the same bytes so downstream handlers can still read the body.
        request._receive = receive  # type: ignore[attr-defined]
        return body


async def _log_incoming_request(request: Request, request_id: str) -> None:
        # Only capture (and replay) the body for methods that actually carry one.
        # Overriding ``request._receive`` on bodyless requests such as the SSE
        # ``GET /events/stream`` breaks Starlette's disconnect listener with a
        # "Unexpected message received: http.request" error.
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


def _utcnow() -> datetime:
        return datetime.now(timezone.utc)


# Map the leading path segment to a PEEL action domain.
_DOMAIN_BY_PREFIX = {
        "resources": "resource",
        "agents": "agent",
        "memory": "memory",
        "documents": "document",
        "events": "resource",
        "executions": "agent",
        "organizations": "organization",
        "identities": "identity",
}

# Map HTTP verbs to PEEL action verbs.
_VERB_BY_METHOD = {
        "GET": "read",
        "HEAD": "read",
        "POST": "create",
        "PUT": "update",
        "PATCH": "update",
        "DELETE": "delete",
}

_PUBLIC_PATHS = {
        "/docs", 
        "/openapi.json", 
        "/redoc"
}

_PUBLIC_PREFIXES = (
        "/health",
        # Auth endpoints that must be reachable without a valid session.
        "/auth/login",
        "/auth/logout",
        "/auth/jwks",
        "/auth/me",
        "/auth/session",
        # Backwards-compatible development endpoints.
        "/auth/dev/login",
        "/auth/dev/principals",
)


def _is_public_request_path(request: Request) -> bool:
        if request.method == "OPTIONS":
                return True
        
        path = request.url.path

        if path in _PUBLIC_PATHS:
                return True
        
        return any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)


def _derive_authorization(request: Request) -> tuple[str, str] | None:
        """Derive an (action, resource_grn) pair for a coarse PEEL pre-check.

        Returns None when the request should not be PEEL-checked at the gateway
        (e.g. unknown/unmapped routes), in which case fine-grained command-level
        PEEL inside the Dispatcher remains the authority.
        """
        path = request.url.path.strip("/")
        if not path:
                return None
        segments = path.split("/")
        domain = _DOMAIN_BY_PREFIX.get(segments[0])
        if domain is None:
                return None

        verb = _VERB_BY_METHOD.get(request.method.upper(), "read")
        # Special-case agent execution which requires the execute capability.
        if domain == "agent" and request.method.upper() == "POST" and segments[-1] == "execute":
                verb = "execute"

        action = f"{domain}:{verb}"

        # Attempt to recover a resource GRN from the path for tenant isolation.
        resource_grn = ""
        if len(segments) > 1:
                candidate = "/".join(segments[1:])
                if candidate.startswith("grn:"):
                        # Strip a trailing sub-action like ".../execute".
                        if candidate.endswith("/execute"):
                                candidate = candidate[: -len("/execute")]
                        resource_grn = candidate
        return action, resource_grn


def _parse_correlation_id(raw: str | None) -> UUID:
        if not raw:
                return uuid4()
        try:
                return UUID(raw)
        except ValueError:
                return uuid4()


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

                        # Accept a signed token from the Authorization header
                        # (SDK/programmatic clients) or the session cookie (browsers).
                        token = extract_bearer_token(request.headers.get("authorization"))
                        if token is None:
                                cookie_name = identity_service.settings.session_cookie_name
                                token = request.cookies.get(cookie_name)

                        auth_result = authenticate_token(identity_service, token)

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
                                capabilities=frozenset(cap.value for cap in auth_result.principal.capabilities),
                                metadata={
                                        "request_id": request_id,
                                        "path": request.url.path,
                                        "method": request.method,
                                },
                        )
                except AuthenticationError:
                        # Public endpoints bypass bearer-token authentication.
                        if _is_public_request_path(request):
                                return await call_next(request)
                        return JSONResponse(status_code=401, content={"detail": "Unauthorized", "request_id": request_id})

                # Coarse PEEL authorization pass at the gateway (defense in depth).
                # Fine-grained, command-level PEEL still runs inside the Dispatcher for
                # every state-changing command. For read (GET) requests this middleware
                # pass is the primary enforcement point since reads do not dispatch
                # commands.
                peel = getattr(request.app.state, "peel", None)
                if peel is not None and not _is_public_request_path(request):
                        authz = _derive_authorization(request)
                        if authz is not None:
                                action, resource_grn = authz
                                try:
                                        await peel.authorize(
                                                request.state.execution_context,
                                                action,
                                                resource_grn,
                                        )
                                except UnauthorizedError as exc:
                                        return JSONResponse(
                                                status_code=403,
                                                content={"detail": str(exc), "request_id": request_id},
                                        )

                return await call_next(request)


def register_middleware(app: FastAPI) -> None:
        app.add_middleware(RequestContextMiddleware)

        app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                #         "http://localhost:3000",
                # ],
                allow_credentials=True,
                allow_methods=[
                        "GET",
                        "POST",
                        "PUT",
                        "PATCH",
                        "DELETE",
                        "OPTIONS"
                ],
                allow_headers=[
                        "Authorization",
                        "Content-Type",
                        "X-Request-ID",
                        "X-Capabilities-ID",
                        "X-Principal-Name",
                ],
                expose_headers=[
                        "X-Request-ID",
                ],
        )
