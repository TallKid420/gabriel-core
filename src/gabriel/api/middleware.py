from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from gabriel.api.auth import AuthenticationError, authenticate_bearer_token
from gabriel.policy.exceptions import UnauthorizedError
from gabriel.runtime.context import ExecutionContext


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

_PUBLIC_PATHS = {"/docs", "/openapi.json", "/redoc"}
_PUBLIC_PREFIXES = ("/health", "/auth/dev/login", "/auth/session", "/auth/logout")


def _is_public_request_path(path: str) -> bool:
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
                request_id = request.headers.get("x-request-id", str(uuid4()))
                request.state.request_id = request_id
                request.state.execution_context = None

                try:
                        auth_result = authenticate_bearer_token(
                                authorization=request.headers.get("authorization"),
                                x_capabilities=request.headers.get("x-capabilities"),
                                x_principal_name=request.headers.get("x-principal-name"),
                        )

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
                        if _is_public_request_path(request.url.path):
                                return await call_next(request)
                        return JSONResponse(status_code=401, content={"detail": "Unauthorized", "request_id": request_id})

                # Coarse PEEL authorization pass at the gateway (defense in depth).
                # Fine-grained, command-level PEEL still runs inside the Dispatcher for
                # every state-changing command. For read (GET) requests this middleware
                # pass is the primary enforcement point since reads do not dispatch
                # commands.
                peel = getattr(request.app.state, "peel", None)
                if peel is not None and not _is_public_request_path(request.url.path):
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
        app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
        )
        app.add_middleware(RequestContextMiddleware)
