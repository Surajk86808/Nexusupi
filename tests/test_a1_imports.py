"""
Task A1 Validation: Import resolution and circular dependency check.
"""

import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_no_circular_dependencies():
    """Validate app modules import without circular dependencies."""
    # Import order matters: base first, then main (which may pull in others)
    from app.models.base import Base  # noqa: F401
    from app.main import app  # noqa: F401
    # If we get here without ImportError, no circular deps in core bootstrap
    assert True


def test_all_packages_importable():
    """Validate all required packages can be imported."""
    import fastapi
    import uvicorn
    import sqlalchemy
    import asyncpg
    import alembic
    import redis
    import arq
    import jwt
    import httpx
    import pydantic
    import pydantic_settings
    import structlog
    import dotenv
    assert fastapi
    assert uvicorn
    assert sqlalchemy
    assert asyncpg
    assert alembic
    assert redis
    assert arq
    assert jwt
    assert httpx
    assert pydantic
    assert pydantic_settings
    assert structlog
    assert dotenv


def test_app_imports():
    """Validate app modules import without circular dependencies."""
    from app.main import app, create_app
    from app.models.base import Base, TimestampMixin, UUIDMixin
    assert app is not None
    assert create_app is not None
    assert Base is not None
    assert TimestampMixin is not None
    assert UUIDMixin is not None


def test_fastapi_app_creation():
    """Validate FastAPI app can be created and has expected structure."""
    from fastapi.testclient import TestClient
    from app.main import create_app
    app = create_app()
    assert app.title == "NexusAPI"
    assert app.version == "0.1.0"
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"
