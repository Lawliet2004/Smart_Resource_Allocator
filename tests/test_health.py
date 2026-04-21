"""Smoke tests for health endpoints."""

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["service"] == "smart-resource-allocator"


def test_health_db_connects_to_postgres(client: TestClient) -> None:
    response = client.get("/health/db")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["db"] == "connected"
    assert body["result"] == 1
