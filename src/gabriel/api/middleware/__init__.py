from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gabriel.api.middleware.authorization import RequestContextMiddleware


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestContextMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Request-ID",
            "X-Capabilities-ID",
            "X-Principal-Name",
            "X-Correlation-ID",
        ],
        expose_headers=["X-Request-ID"],
    )


__all__ = ["register_middleware", "RequestContextMiddleware"]