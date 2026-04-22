"""Web session helpers."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User

SESSION_COOKIE = "sra_session"
DbSession = Annotated[Session, Depends(get_db)]

ROLE_HOME = {
    "volunteer": "/v/",
    "coordinator": "/c/",
    "admin": "/a/",
}


def get_current_user(request: Request, db: Session) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None

    user_id = decode_access_token(token)
    if user_id is None:
        return None

    user = db.get(User, user_id)
    if user is None or not user.is_active or user.role not in ROLE_HOME:
        return None
    return user


def role_home(user: User) -> str:
    return ROLE_HOME.get(user.role, "/login")


def login_path(next_path: str | None = None) -> str:
    if not next_path:
        return "/login"
    return f"/login?next={next_path}"
