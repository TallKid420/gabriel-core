from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import APIRouter, FastAPI

from gabriel.api.dependencies import initialize_gateway_state
from gabriel.api.errors import register_exception_handlers
from gabriel.api.middleware import register_middleware
from gabriel.api.routers import (
    agents,
    agent_specs,
    conversations,
    memory_layers,
    documents,
    events,
    executions,
    health,
    auth,
    memory,
    organizations,
    resources,
    users,
    chat,
    notifications,
)

def register_routers(app: FastAPI) -> None:
    # Keep health at root for infra probes while versioning all other routes.
    app.include_router(health.router)

    v1 = APIRouter(prefix="/api/v1")
    v1.include_router(resources.router)
    v1.include_router(agents.router)
    v1.include_router(agent_specs.router)
    v1.include_router(documents.router)
    v1.include_router(conversations.router)
    # memory_layers must be registered before the legacy /memory router so the
    # more specific /memory/layers prefix wins.
    v1.include_router(memory_layers.router)
    v1.include_router(memory.router)
    v1.include_router(events.router)
    v1.include_router(executions.router)
    v1.include_router(organizations.router)
    v1.include_router(users.router)
    v1.include_router(auth.router)
    v1.include_router(chat.router)
    v1.include_router(notifications.router)
    app.include_router(v1)


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
