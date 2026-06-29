from __future__ import annotations

from fastapi import FastAPI

from gabriel.api.dependencies import initialize_gateway_state
from gabriel.api.errors import register_exception_handlers
from gabriel.api.middleware import register_middleware
from gabriel.api.routers import (
    agents,
    events,
    executions,
    health,
    identities,
    memory,
    organizations,
    resources,
)


def register_routers(app: FastAPI) -> None:
    app.include_router(health.router)
    app.include_router(resources.router)
    app.include_router(agents.router)
    app.include_router(memory.router)
    app.include_router(events.router)
    app.include_router(executions.router)
    app.include_router(organizations.router)
    app.include_router(identities.router)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Gabriel",
        version="0.1.0",
        description="Gabriel API Gateway exposes Gabriel resources and commands.",
    )
    initialize_gateway_state(app)
    register_middleware(app)
    register_exception_handlers(app)
    register_routers(app)
    return app


app = create_app()
