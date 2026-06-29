from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from gabriel.api.auth import AuthenticationError, authenticate_bearer_token
from gabriel.runtime.context import ExecutionContext


def _utcnow() -> datetime:
	return datetime.now(timezone.utc)


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
			# Health and documentation endpoints remain public.
			if request.url.path.startswith("/health") or request.url.path in {
				"/docs",
				"/openapi.json",
				"/redoc",
			}:
				return await call_next(request)
			return JSONResponse(status_code=401, content={"detail": "Unauthorized", "request_id": request_id})

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
