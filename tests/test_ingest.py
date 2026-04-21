"""Tests for the /api/ingest/ endpoint (extractor + matcher end-to-end)."""

from sqlalchemy import text

from app.core.database import SessionLocal


def _reset_tables() -> None:
    """Wipe tasks + volunteers between tests so ordering doesn't matter."""
    db = SessionLocal()
    try:
        db.execute(text("TRUNCATE TABLE tasks RESTART IDENTITY CASCADE"))
        db.execute(text("TRUNCATE TABLE volunteers RESTART IDENTITY CASCADE"))
        db.commit()
    finally:
        db.close()


def test_ingest_creates_task_and_matches_by_skill_and_location(client):
    _reset_tables()

    # Seed two volunteers: one matches, one doesn't.
    from app.models.volunteer import Volunteer
    db = SessionLocal()
    try:
        db.add_all([
            Volunteer(
                name="Match Me",
                location="Downtown",
                skills=["water_rescue"],
                is_available=True,
            ),
            Volunteer(
                name="Wrong Location",
                location="North Side",
                skills=["water_rescue"],
                is_available=True,
            ),
        ])
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/api/ingest/",
        json={"raw_text": "Urgent flood downtown, need water rescue help"},
    )

    assert response.status_code == 200
    body = response.json()

    # Task was extracted
    assert body["task"]["urgency"] == 5
    assert body["task"]["location"] == "Downtown"
    assert "water_rescue" in body["task"]["required_skills"]

    # Only the downtown volunteer was matched
    names = [v["name"] for v in body["matched_volunteers"]]
    assert names == ["Match Me"]
