"""Shared pytest fixtures."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web.rate_limit import limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear slowapi's in-memory buckets so per-IP limits don't leak between tests."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
