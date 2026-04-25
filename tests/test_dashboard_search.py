from app.models.task import Task
from app.models.volunteer import Volunteer
from sqlalchemy import select
from app.core.database import SessionLocal
from tests.test_web import _reset_web_tables

def test_dashboard_search_htmx(client):
    _reset_web_tables()

    # Register volunteer
    client.post(
        "/register",
        data={
            "consent": "on",
            "email": "dash-volunteer@example.com",
            "password": "password123",
            "role": "volunteer",
            "name": "Dash Volunteer",
        },
        headers={"X-Forwarded-For": "198.51.100.42"},
    )

    db = SessionLocal()
    try:
        volunteer = db.scalar(select(Volunteer).where(Volunteer.name == "Dash Volunteer"))
        assert volunteer is not None
        volunteer.location = "Uptown"
        volunteer.skills = ["general_support"]
        db.add_all(
            [
                Task(
                    title="Clean Park",
                    description="Cleaning the park",
                    location="Uptown",
                    status="open",
                    urgency=3,
                    people_needed=5,
                ),
                Task(
                    title="Paint Fence",
                    description="Painting the park fence",
                    location="Uptown",
                    status="open",
                    urgency=2,
                    people_needed=2,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    # Request dashboard without filter
    res = client.get("/v/")
    assert res.status_code == 200
    assert "Clean Park" in res.text
    assert "Paint Fence" in res.text

    # Request dashboard with filter (HTMX)
    res_htmx = client.get("/v/?q=Clean", headers={"HX-Request": "true"})
    assert res_htmx.status_code == 200
    assert "Clean Park" in res_htmx.text
    assert "Paint Fence" not in res_htmx.text

    # Request dashboard with another filter (HTMX)
    res_htmx2 = client.get("/v/?q=Paint", headers={"HX-Request": "true"})
    assert res_htmx2.status_code == 200
    assert "Paint Fence" in res_htmx2.text
    assert "Clean Park" not in res_htmx2.text
