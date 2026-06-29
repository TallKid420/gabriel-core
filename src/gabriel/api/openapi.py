from __future__ import annotations

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def install_openapi_factory(app: FastAPI) -> None:
    # This module customizes the OpenAPI document exposed by FastAPI.
    # It is documentation/spec generation only (for /openapi.json, Swagger UI, SDK tooling).
    # It does NOT run models, execute agents, or participate in AI response generation.
    def custom_openapi() -> dict:
        # Cache the schema after first build to avoid regenerating on every request.
        if app.openapi_schema:
            return app.openapi_schema

        # Build baseline OpenAPI schema from app metadata + registered routes.
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        # API contract metadata for clients/tooling.
        schema["servers"] = [{"url": "/", "description": "Default server"}]
        # Vendor extension describing our architectural contract.
        schema["x-gabriel-contract"] = "resource-first"
        app.openapi_schema = schema
        return app.openapi_schema

    # Override FastAPI's default OpenAPI factory with our customized version.
    app.openapi = custom_openapi
