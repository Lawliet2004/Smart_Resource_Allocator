"""Smoke tests for the HTML web layer."""

from urllib.parse import parse_qs, urlparse

from sqlalchemy import select, text

from app.core.database import SessionLocal
from app.models.assignment import Assignment
from app.models.task import Task


def _reset_web_tables() -> None:
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


def test_public_pages_render(client):
    assert client.get("/login").status_code == 200
    assert client.get("/register").status_code == 200


def test_register_rejects_admin_role(client):
    _reset_web_tables()

    response = client.post(
        "/register",
        data={
            "consent": "on",
            "email": "root@example.com",
            "password": "password123",
            "role": "admin",
            "name": "Root",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "valid role" in response.text.lower()


def test_protected_routes_redirect_to_login(client):
    for path in ["/", "/v/", "/c/", "/a/"]:
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"].startswith("/login")


def test_volunteer_registration_and_dashboard(client):
    _reset_web_tables()

    r = client.post(
        "/register",
        data={
            "consent": "on",
            "email": "alice@example.com",
            "password": "password123",
            "role": "volunteer",
            "name": "Alice",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/v/"
    assert "sra_session" in r.cookies

    # Follow the redirect; cookie carries over in TestClient
    dashboard = client.get("/v/")
    assert dashboard.status_code == 200
    assert "Volunteer Dashboard" in dashboard.text
    assert "Alice" in dashboard.text


def test_coordinator_registration_and_dashboard(client):
    _reset_web_tables()

    r = client.post(
        "/register",
        data={
            "consent": "on",
            "email": "bob@example.com",
            "password": "password123",
            "role": "coordinator",
            "name": "Bob",
            "org_name": "Helping Hands",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/c/"

    dashboard = client.get("/c/")
    assert dashboard.status_code == 200
    assert "Helping Hands" in dashboard.text or "Dashboard" in dashboard.text


def test_login_rejects_bad_password(client):
    _reset_web_tables()

    client.post(
        "/register",
        data={
            "consent": "on",
            "email": "carol@example.com",
            "password": "password123",
            "role": "volunteer",
            "name": "Carol",
        },
    )
    # Log out to clear cookie from TestClient
    client.post("/logout")

    r = client.post(
        "/login",
        data={"email": "carol@example.com", "password": "wrong-password"},
        follow_redirects=False,
    )
    assert r.status_code == 401
    assert "incorrect" in r.text.lower()


def test_login_ignores_unsafe_next_redirects(client):
    _reset_web_tables()

    client.post(
        "/register",
        data={
            "consent": "on",
            "email": "eve@example.com",
            "password": "password123",
            "role": "volunteer",
            "name": "Eve",
        },
    )

    client.post("/logout")
    protocol_relative = client.post(
        "/login",
        data={"email": "eve@example.com", "password": "password123", "next": "//evil.com"},
        follow_redirects=False,
    )
    assert protocol_relative.status_code == 303
    assert protocol_relative.headers["location"] == "/v/"

    client.post("/logout")
    backslash_variant = client.post(
        "/login",
        data={"email": "eve@example.com", "password": "password123", "next": "/\\evil.com"},
        follow_redirects=False,
    )
    assert backslash_variant.status_code == 303
    assert backslash_variant.headers["location"] == "/v/"

    client.post("/logout")
    encoded = client.post(
        "/login",
        data={"email": "eve@example.com", "password": "password123", "next": "%2F%2Fevil.com"},
        follow_redirects=False,
    )
    assert encoded.status_code == 303
    assert encoded.headers["location"] == "/v/"


def test_role_isolation_volunteer_cannot_see_coordinator(client):
    _reset_web_tables()

    # Register as volunteer
    client.post(
        "/register",
        data={
            "consent": "on",
            "email": "dave@example.com",
            "password": "password123",
            "role": "volunteer",
            "name": "Dave",
        },
    )
    # Volunteer visits coordinator dashboard -> redirect to / (then to their own dashboard)
    r = client.get("/c/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"


def test_coordinator_rejects_invalid_task_status(client):
    _reset_web_tables()

    client.post(
        "/register",
        data={
            "consent": "on",
            "email": "coord-status@example.com",
            "password": "password123",
            "role": "coordinator",
            "name": "Coord",
            "org_name": "Status Org",
        },
    )
    client.post(
        "/c/tasks/new",
        data={
            "title": "Status Test Task",
            "description": "Desc",
            "location": "Downtown",
            "urgency": "3",
            "required_skills": "water_rescue",
        },
        follow_redirects=False,
    )

    db = SessionLocal()
    try:
        task = db.scalar(select(Task).where(Task.title == "Status Test Task"))
        assert task is not None
        task_id = task.id
    finally:
        db.close()

    response = client.post(
        f"/c/tasks/{task_id}/status",
        data={"status": "not-a-real-status"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    redirect_parts = urlparse(response.headers["location"])
    redirect_query = parse_qs(redirect_parts.query)
    assert redirect_parts.path == "/c/"
    assert redirect_query.get("error") == ["Invalid task status."]

    db = SessionLocal()
    try:
        unchanged = db.get(Task, task_id)
        assert unchanged is not None
        assert unchanged.status == "open"
    finally:
        db.close()


def test_volunteer_cannot_apply_to_closed_task(client):
    _reset_web_tables()

    db = SessionLocal()
    try:
        task = Task(
            title="Closed Task",
            description="No longer accepting applications",
            status="closed",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id
    finally:
        db.close()

    client.post(
        "/register",
        data={
            "consent": "on",
            "email": "closed-apply@example.com",
            "password": "password123",
            "role": "volunteer",
            "name": "Closed Apply",
        },
    )

    response = client.post(f"/v/tasks/{task_id}/apply", follow_redirects=False)
    assert response.status_code == 303
    redirect_parts = urlparse(response.headers["location"])
    redirect_query = parse_qs(redirect_parts.query)
    assert redirect_parts.path == f"/v/tasks/{task_id}"
    assert redirect_query.get("error") == ["Task is not open for applications."]

    db = SessionLocal()
    try:
        assignment_count = db.scalar(select(Assignment.id).where(Assignment.task_id == task_id))
        assert assignment_count is None
    finally:
        db.close()
