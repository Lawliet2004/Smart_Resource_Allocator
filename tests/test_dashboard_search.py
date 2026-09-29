from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.task import Task
from app.models.volunteer import Volunteer


def test_dashboard_search_htmx(client):
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


def _register_volunteer(client, email: str, name: str, ip: str) -> None:
    response = client.post(
        "/register",
        data={
            "consent": "on",
            "email": email,
            "password": "password123",
            "role": "volunteer",
            "name": name,
        },
        headers={"X-Forwarded-For": ip},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _seed_tasks(volunteer_name: str) -> None:
    db = SessionLocal()
    try:
        volunteer = db.scalar(select(Volunteer).where(Volunteer.name == volunteer_name))
        assert volunteer is not None
        volunteer.location = "Uptown"
        volunteer.skills = ["general_support"]
        db.add_all(
            [
                Task(
                    title="Clean Park",
                    description="Sweeping the riverside path",
                    location="Uptown",
                    status="open",
                    urgency=3,
                    people_needed=5,
                ),
                Task(
                    title="Paint Fence",
                    description="Repainting the boundary wall",
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


def test_dashboard_search_matches_description_like_the_task_list(client):
    _register_volunteer(client, "desc-vol@example.com", "Desc Vol", "198.51.100.61")
    _seed_tasks("Desc Vol")

    # "riverside" only appears in a description, never in a title.
    dashboard = client.get("/v/?q=riverside", headers={"HX-Request": "true"})
    assert dashboard.status_code == 200
    assert "Clean Park" in dashboard.text
    assert "Paint Fence" not in dashboard.text

    # The full task list must agree with the dashboard quick-search.
    task_list = client.get("/v/tasks?q=riverside")
    assert task_list.status_code == 200
    assert "Clean Park" in task_list.text
    assert "Paint Fence" not in task_list.text


def test_search_wildcards_are_escaped_not_interpreted(client):
    _register_volunteer(client, "wild-vol@example.com", "Wild Vol", "198.51.100.62")
    _seed_tasks("Wild Vol")

    # A bare "%" must be a literal, not "match every row".
    response = client.get("/v/?q=%25", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Clean Park" not in response.text
    assert "Paint Fence" not in response.text

    # "_" likewise must not act as a single-character wildcard.
    underscore = client.get("/v/?q=Clean_Park", headers={"HX-Request": "true"})
    assert "Clean Park" not in underscore.text


def test_overlong_search_is_truncated_not_rejected(client):
    _register_volunteer(client, "long-vol@example.com", "Long Vol", "198.51.100.63")
    _seed_tasks("Long Vol")

    response = client.get("/v/?q=" + "z" * 5000, headers={"HX-Request": "true"})
    assert response.status_code == 200
