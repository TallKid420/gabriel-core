from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI

from gabriel.api.dependencies import initialize_gateway_state
from gabriel.api.errors import register_exception_handlers
from gabriel.api.middleware import register_middleware
from gabriel.api.routers import (
    agents,
    documents,
    events,
    executions,
    health,
    auth,
    memory,
    organizations,
    resources,
    chat,
    notifications,
)

def register_routers(app: FastAPI) -> None:
    app.include_router(health.router)
    app.include_router(resources.router)
    app.include_router(agents.router)
    app.include_router(documents.router)
    app.include_router(memory.router)
    app.include_router(events.router)
    app.include_router(executions.router)
    app.include_router(organizations.router)
    app.include_router(auth.router)
    app.include_router(chat.router)
    app.include_router(notifications.router)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await initialize_gateway_state(app)
        yield

    app = FastAPI(
        title="Gabriel",
        version="0.1.0",
        description="Gabriel API Gateway exposes Gabriel resources and commands.",
        lifespan=lifespan,
    )
    register_middleware(app)
    register_exception_handlers(app)
    register_routers(app)
    return app


app = create_app()
