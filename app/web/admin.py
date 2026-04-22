"""Admin pages."""

from fastapi import APIRouter, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select, text

from app.core.config import settings
from app.models.organization import Organization
from app.models.user import User
from app.web.deps import DbSession, get_current_user, login_path
from app.web.templates import context, templates

router = APIRouter()


def require_admin(request: Request, db: DbSession) -> User | RedirectResponse:
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(
            login_path(str(request.url.path)), status_code=status.HTTP_303_SEE_OTHER
        )
    if user.role != "admin":
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return user


@router.get("/")
def dashboard(request: Request, db: DbSession):
    user = require_admin(request, db)
    if isinstance(user, RedirectResponse):
        return user

    users = db.execute(
        select(User)
        .order_by(User.created_at.desc())
        .limit(settings.ADMIN_LIST_LIMIT)
    ).scalars().all()
    organizations = (
        db.execute(
            select(Organization)
            .order_by(Organization.created_at.desc())
            .limit(settings.ADMIN_LIST_LIMIT)
        ).scalars().all()
    )
    user_count = db.scalar(select(func.count(User.id))) or 0
    organization_count = db.scalar(select(func.count(Organization.id))) or 0
    db_result = db.execute(text("SELECT 1")).scalar()
    return templates.TemplateResponse(
        "admin/dashboard.html",
        context(
            request,
            user,
            users=users,
            organizations=organizations,
            user_count=user_count,
            organization_count=organization_count,
            db_ok=db_result == 1,
        ),
    )


@router.post("/users/{user_id}/toggle")
def toggle_user(user_id: int, request: Request, db: DbSession):
    user = require_admin(request, db)
    if isinstance(user, RedirectResponse):
        return user

    target = db.get(User, user_id)
    if target is None:
        return RedirectResponse("/a/?error=User not found.", status_code=status.HTTP_303_SEE_OTHER)
    if target.id == user.id:
        return RedirectResponse(
            "/a/?error=You cannot change your own account status.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    target.is_active = not target.is_active
    db.commit()
    return RedirectResponse("/a/?message=User updated.", status_code=status.HTTP_303_SEE_OTHER)
