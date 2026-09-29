"""Shared pytest fixtures."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.main import app
from app.web.csrf import CSRF_COOKIE, CSRF_FIELD
from app.web.rate_limit import limiter

WEB_TABLES = ("assignments", "tasks", "volunteers", "organizations", "users")


def reset_web_tables() -> None:
    """Truncate every application table so each test starts from a clean slate."""
    db = SessionLocal()
    try:
        for table in WEB_TABLES:
            db.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))
        db.commit()
    finally:
        db.close()


class CsrfClient(TestClient):
    """TestClient that fills in the CSRF token the way a real browser form does.

    Tests exercise the middleware for real; they just don't have to hand-copy
    the token into every ``data=`` dict. Pass ``csrf_token=None`` in the data to
    deliberately submit without one.
    """

    def _token(self) -> str:
        token = self.cookies.get(CSRF_COOKIE)
        if not token:
            self.get("/login")
            token = self.cookies.get(CSRF_COOKIE)
        return token or ""

    def post(self, url: str, **kwargs: Any):  # type: ignore[override]
        data = kwargs.get("data")
        if isinstance(data, dict) and CSRF_FIELD not in data:
            kwargs["data"] = {**data, CSRF_FIELD: self._token()}
        elif data is None and "json" not in kwargs and "content" not in kwargs:
            kwargs["data"] = {CSRF_FIELD: self._token()}
        return super().post(url, **kwargs)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear slowapi's in-memory buckets so per-IP limits don't leak between tests."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(autouse=True)
def _clean_database():
    """Every test gets an empty database; no test has to remember to reset."""
    reset_web_tables()
    yield


@pytest.fixture
def client() -> CsrfClient:
    return CsrfClient(app)


@pytest.fixture
def raw_client() -> TestClient:
    """Client that does *not* auto-attach CSRF tokens, for testing the guard."""
    return TestClient(app)
