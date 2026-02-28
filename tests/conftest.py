"""
Pytest configuration and fixtures.
"""

import os
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Set minimal env for app bootstrap when running full test suite
# (individual tests may override via monkeypatch)
_env_set = False


def pytest_configure(config):
    """Set default env vars for tests if not already set."""
    global _env_set
    if _env_set:
        return
    defaults = {
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/nexusapi_test",
        "REDIS_URL": "redis://localhost:6379/0",
        "JWT_SECRET": "a" * 32,
    }
    for k, v in defaults.items():
        if k not in os.environ:
            os.environ[k] = v
    _env_set = True
