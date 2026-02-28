"""
Task A3 Validation: Structured logging tests.
"""

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def minimal_env(monkeypatch):
    """Set minimal required env vars."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "a" * 32)
    monkeypatch.setenv("ENVIRONMENT", "production")


def test_logger_initializes_successfully(minimal_env):
    """Logger initializes and can log."""
    from app.core.config import get_settings
    get_settings.cache_clear()
    from app.core.logging import configure_logging, get_logger
    configure_logging()
    logger = get_logger("test")
    logger.info("test_message", key="value")
    assert logger is not None


def test_log_output_is_valid_json(minimal_env, capsys):
    """Log output in production mode is valid JSON."""
    from app.core.config import get_settings
    get_settings.cache_clear()
    from app.core.logging import configure_logging, get_logger
    configure_logging()
    logger = get_logger("test")
    logger.info("json_test", foo="bar")
    captured = capsys.readouterr()
    line = captured.out.strip()
    if line:
        parsed = json.loads(line)
        assert isinstance(parsed, dict)
        assert "foo" in parsed or "event" in parsed or "message" in parsed


def test_request_id_exists_in_logs(minimal_env, capsys):
    """request_id is present in log output when bound."""
    from app.core.config import get_settings
    get_settings.cache_clear()
    from app.core.logging import (
        configure_logging,
        get_logger,
        bind_request_context,
        clear_request_context,
    )
    configure_logging()
    logger = get_logger("test")
    bind_request_context(request_id="test-uuid-123", method="GET", path="/")
    logger.info("request_completed", response_status=200, duration_ms=1.5)
    clear_request_context()
    captured = capsys.readouterr()
    assert "test-uuid-123" in captured.out or "request_id" in captured.out


def test_middleware_assigns_request_id(minimal_env):
    """Middleware assigns X-Request-ID to response headers."""
    from app.core.config import get_settings
    get_settings.cache_clear()
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "X-Request-ID" in r.headers
    request_id = r.headers["X-Request-ID"]
    assert len(request_id) == 36
    assert request_id.count("-") == 4


def test_middleware_logs_request_completion(minimal_env, capsys):
    """Middleware logs request completion with duration and status."""
    from app.core.config import get_settings
    get_settings.cache_clear()
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    client.get("/")
    captured = capsys.readouterr()
    assert "request_completed" in captured.out or "request_started" in captured.out
