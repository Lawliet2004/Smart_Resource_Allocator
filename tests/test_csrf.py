"""CSRF protection tests."""

from app.web.csrf import CSRF_COOKIE, CSRF_FIELD, generate_csrf_token, is_valid_csrf_token


def test_html_response_issues_a_csrf_cookie(raw_client):
    response = raw_client.get("/login")
    assert response.status_code == 200
    token = response.cookies.get(CSRF_COOKIE)
    assert token
    assert is_valid_csrf_token(token)


def test_csrf_cookie_is_httponly_and_lax(raw_client):
    response = raw_client.get("/login")
    set_cookie = [
        value
        for key, value in response.headers.multi_items()
        if key.lower() == "set-cookie" and value.startswith(f"{CSRF_COOKIE}=")
    ]
    assert set_cookie, "no CSRF cookie was set"
    assert "HttpOnly" in set_cookie[0]
    assert "SameSite=Lax" in set_cookie[0]


def test_post_without_token_is_rejected(raw_client):
    raw_client.get("/login")
    response = raw_client.post(
        "/login",
        data={"email": "nobody@example.com", "password": "password123"},
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_post_with_forged_token_is_rejected(raw_client):
    raw_client.get("/login")
    response = raw_client.post(
        "/login",
        data={
            "email": "nobody@example.com",
            "password": "password123",
            CSRF_FIELD: generate_csrf_token(),  # correctly signed, but not this session's
        },
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_post_with_unsigned_token_is_rejected(raw_client):
    raw_client.get("/login")
    response = raw_client.post(
        "/login",
        data={
            "email": "nobody@example.com",
            "password": "password123",
            CSRF_FIELD: "made-up-value.deadbeef",
        },
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_post_with_matching_token_is_accepted(raw_client):
    raw_client.get("/login")
    token = raw_client.cookies.get(CSRF_COOKIE)
    response = raw_client.post(
        "/login",
        data={
            "email": "nobody@example.com",
            "password": "wrong-password",
            CSRF_FIELD: token,
        },
        follow_redirects=False,
    )
    # Reaches the handler and fails authentication rather than CSRF validation.
    assert response.status_code == 401


def test_cross_origin_post_is_rejected(raw_client):
    raw_client.get("/login")
    token = raw_client.cookies.get(CSRF_COOKIE)
    response = raw_client.post(
        "/login",
        data={"email": "nobody@example.com", "password": "pw", CSRF_FIELD: token},
        headers={"Origin": "https://evil.example.com"},
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_cross_origin_json_api_post_is_rejected(raw_client):
    response = raw_client.post(
        "/api/ingest/",
        json={"raw_text": "Urgent flood downtown"},
        headers={"Origin": "https://evil.example.com"},
    )
    assert response.status_code == 403


def test_csrf_token_is_rendered_into_forms(raw_client):
    body = raw_client.get("/login").text
    assert f'name="{CSRF_FIELD}"' in body


def test_token_survives_across_requests(raw_client):
    first = raw_client.get("/login").cookies.get(CSRF_COOKIE)
    raw_client.get("/register")
    # A valid token is reused rather than rotated on every render.
    assert raw_client.cookies.get(CSRF_COOKIE) == first
