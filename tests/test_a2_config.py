"""
Task A2 Validation: Configuration module tests.
"""

import os
import sys
from pathlib import Path

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Clear get_settings cache between tests to allow env overrides."""
    from app.core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def minimal_env(monkeypatch):
    """Set minimal required env vars for Settings to load."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "a" * 32)


def test_settings_load_from_env(minimal_env):
    """Settings load correctly from environment."""
    from app.core.config import get_settings
    settings = get_settings()
    assert settings.database_url == "postgresql+asyncpg://user:pass@localhost:5432/test"
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.jwt_secret == "a" * 32
    assert settings.environment == "development"
    assert settings.debug is False
    assert settings.log_level == "INFO"
    assert settings.rate_limit_per_minute == 100


def test_settings_env_overrides(minimal_env, monkeypatch):
    """Environment overrides default values."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "200")
    from app.core.config import get_settings
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.environment == "production"
    assert settings.debug is True
    assert settings.log_level == "DEBUG"
    assert settings.rate_limit_per_minute == 200


def test_missing_required_raises_validation_error(monkeypatch):
    """Missing required variables raises ValidationError."""
    # Clear any inherited env vars
    for key in ("DATABASE_URL", "REDIS_URL", "JWT_SECRET"):
        monkeypatch.delenv(key, raising=False)
    from pydantic import ValidationError
    from app.core.config import Settings
    with pytest.raises(ValidationError):
        Settings()


def test_jwt_secret_min_length_validation(minimal_env, monkeypatch):
    """JWT_SECRET must be at least 32 characters."""
    monkeypatch.setenv("JWT_SECRET", "short")
    from pydantic import ValidationError
    from app.core.config import get_settings
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        get_settings()


def test_singleton_behavior(minimal_env):
    """get_settings returns same instance (cached singleton)."""
    from app.core.config import get_settings
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_settings_import_safe(minimal_env):
    """Settings import works from app.core."""
    from app.core import get_settings, Settings
    settings = get_settings()
    assert isinstance(settings, Settings)


def test_settings_immutable_after_load(minimal_env):
    """Settings are immutable (frozen) - no runtime mutation risk."""
    from app.core.config import get_settings
    settings = get_settings()
    with pytest.raises((AttributeError, TypeError, Exception)):
        settings.database_url = "modified"


def test_fastapi_app_loads_config(minimal_env):
    """FastAPI app loads config successfully at startup (lifespan)."""
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"
