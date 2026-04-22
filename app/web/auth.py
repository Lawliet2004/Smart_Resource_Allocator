"""Authentication pages."""

from urllib.parse import unquote

from fastapi import APIRouter, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.organization import Organization
from app.models.user import User
from app.models.volunteer import Volunteer
from app.web.deps import SESSION_COOKIE, DbSession, get_current_user, role_home
from app.web.forms import form_value, parse_urlencoded_form
from app.web.options import ROLE_OPTIONS
from app.web.templates import context, templates

router = APIRouter()

MAX_EMAIL_CHARS = 255
MAX_NAME_CHARS = 255
MAX_ORG_NAME_CHARS = 255
MAX_PASSWORD_BYTES = 72


def safe_next_path(next_path: str) -> str:
    candidate = unquote(next_path).strip()
    if not candidate:
        return ""
    if not candidate.startswith("/"):
        return ""
    if candidate.startswith("//"):
        return ""
    if "\\" in candidate:
        return ""
    if any(char in candidate for char in "\r\n\t"):
        return ""
    return candidate


@router.get("/")
def index(request: Request, db: DbSession):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(role_home(user), status_code=status.HTTP_303_SEE_OTHER)


@router.get("/register")
def register_page(request: Request, db: DbSession):
    user = get_current_user(request, db)
    if user is not None:
        return RedirectResponse(role_home(user), status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        "auth/register.html",
        context(request, roles=ROLE_OPTIONS),
    )


@router.post("/register")
async def register(request: Request, db: DbSession):
    form = await parse_urlencoded_form(request)
    email = form_value(form, "email").lower()
    password = form_value(form, "password")
    role = form_value(form, "role", "volunteer")
    name = form_value(form, "name") or email.split("@")[0]
    org_name = form_value(form, "org_name") or "My NGO"
    consent = form_value(form, "consent")

    if not consent:
        return templates.TemplateResponse(
            "auth/register.html",
            context(
                request,
                roles=ROLE_OPTIONS,
                error="You must consent to data processing to register.",
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if role not in {value for value, _label in ROLE_OPTIONS}:
        return templates.TemplateResponse(
            "auth/register.html",
            context(request, roles=ROLE_OPTIONS, error="Choose a valid role."),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if (
        not email
        or "@" not in email
        or len(email) > MAX_EMAIL_CHARS
        or len(name) > MAX_NAME_CHARS
        or len(org_name) > MAX_ORG_NAME_CHARS
        or len(password) < 8
        or len(password.encode("utf-8")) > MAX_PASSWORD_BYTES
    ):
        return templates.TemplateResponse(
            "auth/register.html",
            context(
                request,
                roles=ROLE_OPTIONS,
                error=(
                    "Use a valid email, a password from 8 to 72 bytes, "
                    "and names under 255 characters."
                ),
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        return templates.TemplateResponse(
            "auth/register.html",
            context(request, roles=ROLE_OPTIONS, error="That email is already registered."),
            status_code=status.HTTP_409_CONFLICT,
        )

    user = User(email=email, password_hash=hash_password(password), role=role)
    try:
        db.add(user)
        db.flush()

        if role == "volunteer":
            db.add(Volunteer(user_id=user.id, name=name, skills=[]))
        elif role == "coordinator":
            db.add(Organization(name=org_name, created_by_id=user.id))

        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            "auth/register.html",
            context(request, roles=ROLE_OPTIONS, error="That email is already registered."),
            status_code=status.HTTP_409_CONFLICT,
        )

    db.refresh(user)

    response = RedirectResponse(role_home(user), status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        SESSION_COOKIE,
        create_access_token(user.id),
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.JWT_EXPIRE_MINUTES * 60,
    )
    return response


@router.get("/login")
def login_page(request: Request, db: DbSession):
    user = get_current_user(request, db)
    if user is not None:
        return RedirectResponse(role_home(user), status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("auth/login.html", context(request))


@router.post("/login")
async def login(request: Request, db: DbSession):
    form = await parse_urlencoded_form(request)
    email = form_value(form, "email").lower()
    password = form_value(form, "password")
    next_path = safe_next_path(form_value(form, "next"))

    if (
        not email
        or len(email) > MAX_EMAIL_CHARS
        or len(password.encode("utf-8")) > MAX_PASSWORD_BYTES
    ):
        return templates.TemplateResponse(
            "auth/login.html",
            context(request, error="Email or password is incorrect."),
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    user = db.scalar(select(User).where(User.email == email))
    home_path = role_home(user) if user is not None else "/login"
    if (
        user is None
        or not user.is_active
        or home_path == "/login"
        or not verify_password(password, user.password_hash)
    ):
        return templates.TemplateResponse(
            "auth/login.html",
            context(request, error="Email or password is incorrect."),
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    response = RedirectResponse(next_path or home_path, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        SESSION_COOKIE,
        create_access_token(user.id),
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.JWT_EXPIRE_MINUTES * 60,
    )
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(SESSION_COOKIE)
    return response
