"""Tests for the /api/ingest/ endpoint (extractor + matcher end-to-end)."""

from sqlalchemy import select, text

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.task import Task


def _reset_tables() -> None:
    """Wipe tasks + volunteers between tests so ordering doesn't matter."""
    db = SessionLocal()
    try:
        db.execute(text("TRUNCATE TABLE assignments RESTART IDENTITY CASCADE"))
        db.execute(text("TRUNCATE TABLE tasks RESTART IDENTITY CASCADE"))
        db.execute(text("TRUNCATE TABLE volunteers RESTART IDENTITY CASCADE"))
        db.execute(text("TRUNCATE TABLE organizations RESTART IDENTITY CASCADE"))
        db.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
        db.commit()
    finally:
        db.close()


def _register_user(client, *, email: str, role: str, name: str) -> None:
    suffix = (sum(ord(ch) for ch in email) % 200) + 1
    response = client.post(
        "/register",
        data={
            "consent": "on",
            "email": email,
            "password": "password123",
            "role": role,
            "name": name,
            "org_name": "Helpers Org",
        },
        headers={"X-Forwarded-For": f"203.0.113.{suffix}"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_ingest_requires_coordinator_auth(client):
    _reset_tables()

    response = client.post(
        "/api/ingest/",
        json={"raw_text": "Urgent flood downtown, need water rescue help"},
    )
    assert response.status_code == 401


def test_ingest_rejects_non_coordinator_user(client):
    _reset_tables()

    _register_user(client, email="vol@example.com", role="volunteer", name="Volunteer")
    response = client.post(
        "/api/ingest/",
        json={"raw_text": "Urgent flood downtown, need water rescue help"},
    )
    assert response.status_code == 403


def test_ingest_rejects_blank_or_oversized_payload(client):
    _reset_tables()

    _register_user(client, email="coord@example.com", role="coordinator", name="Coordinator")

    blank = client.post("/api/ingest/", json={"raw_text": "   "})
    assert blank.status_code == 422

    oversized = client.post(
        "/api/ingest/",
        json={"raw_text": "x" * (settings.MAX_INGEST_CHARS + 1)},
    )
    assert oversized.status_code == 422


def test_ingest_creates_task_and_matches_by_skill_and_location(client):
    _reset_tables()
    _register_user(client, email="coord@example.com", role="coordinator", name="Coordinator")

    # Seed two volunteers: one matches, one doesn't.
    from app.models.volunteer import Volunteer

    db = SessionLocal()
    try:
        db.add_all(
            [
                Volunteer(
                    name="Match Me",
                    location="Downtown",
                    skills=["water_rescue"],
                    is_available=True,
                    phone_number="12345",
                ),
                Volunteer(
                    name="Wrong Location",
                    location="North Side",
                    skills=["water_rescue"],
                    is_available=True,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/api/ingest/",
        json={"raw_text": "Urgent flood downtown, need water rescue help"},
    )

    assert response.status_code == 201
    body = response.json()

    # Task was extracted
    assert body["task"]["urgency"] == 5
    assert body["task"]["location"] == "Downtown"
    assert "water_rescue" in body["task"]["required_skills"]
    assert "raw_text" not in body["task"]
    assert "org_id" not in body["task"]
    assert "created_by_id" not in body["task"]

    # Only the downtown volunteer was matched
    names = [v["name"] for v in body["matched_volunteers"]]
    assert names == ["Match Me"]
    assert "phone_number" not in body["matched_volunteers"][0]
    assert "user_id" not in body["matched_volunteers"][0]

    db = SessionLocal()
    try:
        saved_task = db.scalar(select(Task).order_by(Task.id.desc()))
        assert saved_task is not None
        assert saved_task.raw_text is None
    finally:
        db.close()
