from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from gabriel.events.exceptions import (
        CommandValidationError,
        EventsError,
        HandlerExecutionError,
        HandlerNotFoundError,
)
from gabriel.policy.exceptions import UnauthorizedError


class GabrielAPIError(Exception):
        def __init__(self, message: str, status_code: int = 400) -> None:
                self.message = message
                self.status_code = status_code
                super().__init__(message)

class AuthenticationError(Exception):
	def __init__(self, message: str, status_code: int = 401) -> None:
                self.message = message
                self.status_code = status_code
                super().__init__(message)

def _error_body(request: Request, detail: str) -> dict:
        return {
                "detail": detail,
                "request_id": getattr(request.state, "request_id", None),
        }


def register_exception_handlers(app: FastAPI) -> None:
        @app.exception_handler(GabrielAPIError)
        async def gabriel_api_error_handler(request: Request, exc: GabrielAPIError) -> JSONResponse:
                return JSONResponse(
                        status_code=exc.status_code,
                        content=_error_body(request, exc.message),
                )

        @app.exception_handler(UnauthorizedError)
        async def unauthorized_error(request: Request, exc: UnauthorizedError) -> JSONResponse:
                # PEEL denied the action. 403 = authenticated but not permitted.
                return JSONResponse(
                        status_code=403,
                        content=_error_body(request, str(exc)),
                )

        @app.exception_handler(HandlerNotFoundError)
        async def handler_not_found_error(request: Request, exc: HandlerNotFoundError) -> JSONResponse:
                return JSONResponse(
                        status_code=400,
                        content=_error_body(request, str(exc)),
                )

        @app.exception_handler(CommandValidationError)
        async def command_validation_error(request: Request, exc: CommandValidationError) -> JSONResponse:
                return JSONResponse(
                        status_code=422,
                        content=_error_body(request, str(exc)),
                )

        @app.exception_handler(HandlerExecutionError)
        async def handler_execution_error(request: Request, exc: HandlerExecutionError) -> JSONResponse:
                return JSONResponse(
                        status_code=500,
                        content=_error_body(request, str(exc)),
                )

        @app.exception_handler(EventsError)
        async def events_error(request: Request, exc: EventsError) -> JSONResponse:
                return JSONResponse(
                        status_code=400,
                        content=_error_body(request, str(exc)),
                )

        @app.exception_handler(Exception)
        async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
                return JSONResponse(
                        status_code=500,
                        content=_error_body(request, f"Unexpected error: {exc}"),
                )
