"""Smoke tests for the HTML web layer."""

from urllib.parse import parse_qs, urlparse

from sqlalchemy import func, select, text

from app.core.database import SessionLocal
from app.models.assignment import Assignment
from app.models.organization import Organization
from app.models.task import Task
from app.models.volunteer import Volunteer


def _forwarded_for(ip: str) -> dict[str, str]:
    return {"X-Forwarded-For": ip}


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


def test_login_page_sets_security_headers(client):
    response = client.get("/login")
    assert response.status_code == 200

    assert "Content-Security-Policy" in response.headers
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Permissions-Policy"] == "geolocation=(), camera=(), microphone=()"
    assert "Strict-Transport-Security" not in response.headers


def test_login_rate_limiter_blocks_11th_attempt(client):
    _reset_web_tables()

    target_ip = "198.51.100.23"
    for attempt in range(10):
        response = client.post(
            "/login",
            data={"email": "missing@example.com", "password": "wrong-password"},
            headers={"X-Forwarded-For": target_ip},
            follow_redirects=False,
        )
        assert response.status_code == 401, f"unexpected status on attempt {attempt + 1}"

    blocked = client.post(
        "/login",
        data={"email": "missing@example.com", "password": "wrong-password"},
        headers={"X-Forwarded-For": target_ip},
        follow_redirects=False,
    )
    assert blocked.status_code == 429
    assert "too many requests" in blocked.text.lower()


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
        headers=_forwarded_for("198.51.100.31"),
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
        headers=_forwarded_for("198.51.100.32"),
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


def test_volunteer_can_filter_matched_tasks(client):
    _reset_web_tables()

    client.post(
        "/register",
        data={
            "consent": "on",
            "email": "filter-volunteer@example.com",
            "password": "password123",
            "role": "volunteer",
            "name": "Filter Volunteer",
        },
        headers=_forwarded_for("198.51.100.42"),
    )

    db = SessionLocal()
    try:
        volunteer = db.scalar(select(Volunteer).where(Volunteer.name == "Filter Volunteer"))
        assert volunteer is not None
        volunteer.location = "Downtown"
        volunteer.skills = ["medical_assistance", "food_distribution"]
        db.add_all(
            [
                Task(
                    title="Medical Camp",
                    description="First aid support for residents",
                    location="Downtown",
                    status="open",
                    urgency=5,
                    required_skills=["medical_assistance"],
                    people_needed=2,
                ),
                Task(
                    title="Food Drive",
                    description="Pack and distribute supplies",
                    location="Downtown",
                    status="open",
                    urgency=2,
                    required_skills=["food_distribution"],
                    people_needed=2,
                ),
                Task(
                    title="Water Rescue",
                    location="Downtown",
                    status="open",
                    urgency=5,
                    required_skills=["water_rescue"],
                    people_needed=2,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    all_tasks = client.get("/v/tasks")
    assert all_tasks.status_code == 200
    assert "Medical Camp" in all_tasks.text
    assert "Food Drive" in all_tasks.text
    assert "Water Rescue" not in all_tasks.text

    skill_filtered = client.get("/v/tasks?skill=medical_assistance")
    assert skill_filtered.status_code == 200
    assert "Medical Camp" in skill_filtered.text
    assert "Food Drive" not in skill_filtered.text

    search_filtered = client.get("/v/tasks?q=Food")
    assert search_filtered.status_code == 200
    assert "Food Drive" in search_filtered.text
    assert "Medical Camp" not in search_filtered.text

    urgency_filtered = client.get("/v/tasks?urgency=4")
    assert urgency_filtered.status_code == 200
    assert "Medical Camp" in urgency_filtered.text
    assert "Food Drive" not in urgency_filtered.text


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
        headers=_forwarded_for("198.51.100.33"),
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/c/"

    dashboard = client.get("/c/")
    assert dashboard.status_code == 200
    assert "Helping Hands" in dashboard.text or "Dashboard" in dashboard.text


def test_coordinator_dashboard_shows_analytics_metrics(client):
    _reset_web_tables()

    client.post(
        "/register",
        data={
            "consent": "on",
            "email": "analytics-coord@example.com",
            "password": "password123",
            "role": "coordinator",
            "name": "Analytics Coord",
            "org_name": "Analytics Org",
        },
        headers=_forwarded_for("198.51.100.39"),
    )

    db = SessionLocal()
    try:
        org = db.scalar(select(Organization).where(Organization.name == "Analytics Org"))
        assert org is not None
        volunteer = Volunteer(name="Metrics Volunteer", skills=["medical_assistance"])
        db.add(volunteer)
        db.flush()

        active_task = Task(
            org_id=org.id,
            created_by_id=org.created_by_id,
            title="Medical camp support",
            status="open",
            required_skills=["medical_assistance"],
        )
        completed_task = Task(
            org_id=org.id,
            created_by_id=org.created_by_id,
            title="Logistics wrap-up",
            status="completed",
            required_skills=["logistics"],
        )
        db.add_all([active_task, completed_task])
        db.flush()

        db.add_all(
            [
                Assignment(task_id=active_task.id, volunteer_id=volunteer.id, status="applied"),
                Assignment(
                    task_id=completed_task.id,
                    volunteer_id=volunteer.id,
                    status="completed",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    dashboard = client.get("/c/")
    assert dashboard.status_code == 200
    assert "Analytics" in dashboard.text
    assert "Fill rate" in dashboard.text
    assert "50%" in dashboard.text
    assert "Avg/task" in dashboard.text
    assert "1.0" in dashboard.text
    assert "Medical assistance" in dashboard.text


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
        headers=_forwarded_for("198.51.100.34"),
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
        headers=_forwarded_for("198.51.100.35"),
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
        headers=_forwarded_for("198.51.100.36"),
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
        headers=_forwarded_for("198.51.100.37"),
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
        headers=_forwarded_for("198.51.100.38"),
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


def test_coordinator_cannot_approve_beyond_task_capacity(client):
    _reset_web_tables()

    client.post(
        "/register",
        data={
            "consent": "on",
            "email": "capacity-coord@example.com",
            "password": "password123",
            "role": "coordinator",
            "name": "Capacity Coord",
            "org_name": "Capacity Org",
        },
        headers=_forwarded_for("198.51.100.40"),
    )

    db = SessionLocal()
    try:
        org = db.scalar(select(Organization).where(Organization.name == "Capacity Org"))
        assert org is not None
        first_volunteer = Volunteer(name="Approved Volunteer", skills=[])
        second_volunteer = Volunteer(name="Waiting Volunteer", skills=[])
        db.add_all([first_volunteer, second_volunteer])
        db.flush()

        task = Task(
            org_id=org.id,
            created_by_id=org.created_by_id,
            title="One slot task",
            status="open",
            people_needed=1,
        )
        db.add(task)
        db.flush()

        db.add(
            Assignment(task_id=task.id, volunteer_id=first_volunteer.id, status="approved")
        )
        waiting = Assignment(task_id=task.id, volunteer_id=second_volunteer.id, status="applied")
        db.add(waiting)
        db.commit()
        waiting_id = waiting.id
    finally:
        db.close()

    response = client.post(f"/c/assignments/{waiting_id}/approve", follow_redirects=False)
    assert response.status_code == 303
    redirect_parts = urlparse(response.headers["location"])
    redirect_query = parse_qs(redirect_parts.query)
    assert redirect_query.get("error") == ["Task already has enough approved volunteers."]

    db = SessionLocal()
    try:
        unchanged = db.get(Assignment, waiting_id)
        assert unchanged is not None
        assert unchanged.status == "applied"
    finally:
        db.close()


def test_volunteer_cannot_apply_to_full_task(client):
    _reset_web_tables()

    db = SessionLocal()
    try:
        existing_volunteer = Volunteer(name="Already Approved", skills=[])
        db.add(existing_volunteer)
        db.flush()

        task = Task(title="Full Task", status="open", people_needed=1)
        db.add(task)
        db.flush()
        db.add(Assignment(task_id=task.id, volunteer_id=existing_volunteer.id, status="approved"))
        db.commit()
        task_id = task.id
    finally:
        db.close()

    client.post(
        "/register",
        data={
            "consent": "on",
            "email": "full-task-volunteer@example.com",
            "password": "password123",
            "role": "volunteer",
            "name": "Full Task Volunteer",
        },
        headers=_forwarded_for("198.51.100.41"),
    )

    detail = client.get(f"/v/tasks/{task_id}")
    assert detail.status_code == 200
    assert "Capacity full" in detail.text

    response = client.post(f"/v/tasks/{task_id}/apply", follow_redirects=False)
    assert response.status_code == 303
    redirect_parts = urlparse(response.headers["location"])
    redirect_query = parse_qs(redirect_parts.query)
    assert redirect_query.get("error") == ["Task already has enough approved volunteers."]

    db = SessionLocal()
    try:
        assignment_count = db.scalar(
            select(func.count(Assignment.id)).where(Assignment.task_id == task_id)
        )
        assert assignment_count == 1
    finally:
        db.close()
