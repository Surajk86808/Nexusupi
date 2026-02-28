"""
Task H1 Validation: structured error handling middleware tests.
"""

import sys
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def env_setup(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "a" * 32)
    monkeypatch.setenv("DEBUG", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_not_found_error_response_is_structured():
    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/path-that-does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert set(body.keys()) == {"error", "message", "request_id"}
    assert isinstance(body["error"], str)
    assert isinstance(body["message"], str)
    UUID(body["request_id"])
    assert response.headers.get("X-Request-ID") == body["request_id"]


def test_auth_error_response_includes_request_id():
    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/jobs/7d94f913-a81a-4d68-a77d-1753f050fcb7")

    assert response.status_code == 401
    body = response.json()
    assert set(body.keys()) == {"error", "message", "request_id"}
    UUID(body["request_id"])
    assert response.headers.get("X-Request-ID") == body["request_id"]


def test_unhandled_exception_response_is_structured():
    from app.main import create_app

    app = create_app()

    @app.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    with TestClient(app) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert set(body.keys()) == {"error", "message", "request_id"}
    assert body["message"] == "Internal server error"
    UUID(body["request_id"])
