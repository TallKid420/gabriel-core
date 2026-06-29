from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gabriel.api.app import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer principal://acme/user/alice",
        "X-Capabilities": "read_resource,write_resource,execute_workflow",
        "X-Correlation-ID": "11111111-1111-1111-1111-111111111111",
    }
