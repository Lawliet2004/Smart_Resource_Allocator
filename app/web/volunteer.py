"""Volunteer-facing pages."""

from fastapi import APIRouter, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models.assignment import Assignment
from app.models.task import Task
from app.models.user import User
from app.models.volunteer import Volunteer
from app.web.deps import DbSession, get_current_user, login_path
from app.web.forms import (
    form_bool,
    form_float,
    form_list,
    form_value,
    parse_urlencoded_form,
)
from app.web.options import SKILL_OPTIONS
from app.web.templates import context, templates

router = APIRouter()

VALID_SKILLS = {value for value, _label in SKILL_OPTIONS}
MAX_NAME_CHARS = 255
MAX_PHONE_CHARS = 50
MAX_LOCATION_CHARS = 255


def normalize_skills(skills: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for skill in skills:
        if skill in VALID_SKILLS and skill not in seen:
            deduped.append(skill)
            seen.add(skill)
    return deduped


def normalized_skill_set(skills: list[object] | None) -> set[str]:
    return {
        skill.strip().casefold()
        for skill in (skills or [])
        if isinstance(skill, str) and skill.strip()
    }


def require_volunteer(request: Request, db: DbSession) -> User | RedirectResponse:
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(
            login_path(str(request.url.path)), status_code=status.HTTP_303_SEE_OTHER
        )
    if user.role != "volunteer":
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return user


def get_or_create_profile(user: User, db: DbSession) -> Volunteer:
    profile = db.scalar(select(Volunteer).where(Volunteer.user_id == user.id))
    if profile is not None:
        return profile

    profile = Volunteer(user_id=user.id, name=user.email.split("@")[0], skills=[])
    try:
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Volunteer).where(Volunteer.user_id == user.id))
        if existing is not None:
            return existing
        raise


def task_match_score(task: Task, volunteer: Volunteer) -> int:
    score = 0
    volunteer_skills = normalized_skill_set(volunteer.skills)
    required_skills = normalized_skill_set(task.required_skills)
    if required_skills:
        score += len(required_skills.intersection(volunteer_skills)) * 25
    if task.location and volunteer.location and task.location.lower() == volunteer.location.lower():
        score += 30
    if volunteer.is_available:
        score += 20
    score += max(1, min(task.urgency or 1, 5)) * 5
    return score


def matched_open_tasks(db: DbSession, volunteer: Volunteer) -> list[tuple[Task, int]]:
    stmt = (
        select(Task)
        .where(Task.status.in_(["open", "pending"]))
        .order_by(Task.urgency.desc(), Task.id.desc())
        .limit(settings.VOLUNTEER_TASK_SCAN_LIMIT)
    )
    tasks = db.execute(stmt).scalars().all()
    ranked: list[tuple[Task, int]] = []
    volunteer_skills = normalized_skill_set(volunteer.skills)
    volunteer_location = (volunteer.location or "").strip().casefold()
    for task in tasks:
        required_skills = normalized_skill_set(task.required_skills)
        if required_skills and not required_skills.intersection(volunteer_skills):
            continue
        # Symmetric location filter: if the task specifies a real location,
        # the volunteer must have a matching one. Tasks without a location —
        # or with the extractor sentinel "unknown" — are always eligible, to
        # stay consistent with app/services/matcher.py.
        task_location = (task.location or "").strip().casefold()
        if task_location and task_location != "unknown" and task_location != volunteer_location:
            continue
        ranked.append((task, task_match_score(task, volunteer)))
    return sorted(ranked, key=lambda item: item[1], reverse=True)


@router.get("/")
def dashboard(request: Request, db: DbSession):
    user = require_volunteer(request, db)
    if isinstance(user, RedirectResponse):
        return user

    profile = get_or_create_profile(user, db)
    assignment_count = db.scalar(
        select(func.count(Assignment.id)).where(Assignment.volunteer_id == profile.id)
    ) or 0
    assignments = db.execute(
        select(Assignment, Task)
        .join(Task, Assignment.task_id == Task.id)
        .where(Assignment.volunteer_id == profile.id)
        .order_by(Assignment.applied_at.desc())
        .limit(min(5, settings.VOLUNTEER_ASSIGNMENTS_LIMIT))
    ).all()
    return templates.TemplateResponse(
        "volunteer/dashboard.html",
        context(
            request,
            user,
            profile=profile,
            matched_tasks=matched_open_tasks(db, profile)[:5],
            assignments=assignments,
            assignment_count=assignment_count,
        ),
    )


@router.get("/profile")
def profile_page(request: Request, db: DbSession):
    user = require_volunteer(request, db)
    if isinstance(user, RedirectResponse):
        return user

    profile = get_or_create_profile(user, db)
    return templates.TemplateResponse(
        "volunteer/profile.html",
        context(request, user, profile=profile, skills=SKILL_OPTIONS),
    )


@router.post("/profile")
async def update_profile(request: Request, db: DbSession):
    user = require_volunteer(request, db)
    if isinstance(user, RedirectResponse):
        return user

    profile = get_or_create_profile(user, db)
    form = await parse_urlencoded_form(request)
    name = form_value(form, "name") or profile.name
    phone_number = form_value(form, "phone_number")
    location = form_value(form, "location")
    if (
        len(name) > MAX_NAME_CHARS
        or len(phone_number) > MAX_PHONE_CHARS
        or len(location) > MAX_LOCATION_CHARS
    ):
        return RedirectResponse(
            "/v/profile?error=Name, phone, or location is too long.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    profile.name = name
    profile.phone_number = phone_number or None
    profile.location = location or None
    profile.latitude = form_float(form, "latitude", min_value=-90, max_value=90)
    profile.longitude = form_float(form, "longitude", min_value=-180, max_value=180)
    profile.skills = normalize_skills(form_list(form, "skills"))
    profile.is_available = form_bool(form, "is_available")
    db.commit()
    return RedirectResponse(
        "/v/profile?message=Profile updated.",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/tasks")
def tasks_page(request: Request, db: DbSession):
    user = require_volunteer(request, db)
    if isinstance(user, RedirectResponse):
        return user

    profile = get_or_create_profile(user, db)
    return templates.TemplateResponse(
        "volunteer/tasks.html",
        context(request, user, profile=profile, matched_tasks=matched_open_tasks(db, profile)),
    )


@router.get("/tasks/{task_id}")
def task_detail(task_id: int, request: Request, db: DbSession):
    user = require_volunteer(request, db)
    if isinstance(user, RedirectResponse):
        return user

    profile = get_or_create_profile(user, db)
    task = db.get(Task, task_id)
    if task is None:
        return RedirectResponse(
            "/v/tasks?error=Task not found.", status_code=status.HTTP_303_SEE_OTHER
        )

    assignment = db.scalar(
        select(Assignment).where(
            Assignment.task_id == task.id,
            Assignment.volunteer_id == profile.id,
        )
    )

    if task.status not in ("open", "pending") and assignment is None:
        return RedirectResponse(
            "/v/tasks?error=Task is no longer accepting applications.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return templates.TemplateResponse(
        "volunteer/task_detail.html",
        context(request, user, task=task, profile=profile, assignment=assignment),
    )


@router.post("/tasks/{task_id}/apply")
def apply_to_task(task_id: int, request: Request, db: DbSession):
    user = require_volunteer(request, db)
    if isinstance(user, RedirectResponse):
        return user

    profile = get_or_create_profile(user, db)
    task = db.get(Task, task_id)
    if task is None:
        return RedirectResponse(
            "/v/tasks?error=Task not found.", status_code=status.HTTP_303_SEE_OTHER
        )
    if task.status not in {"open", "pending"}:
        return RedirectResponse(
            f"/v/tasks/{task.id}?error=Task is not open for applications.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    existing = db.scalar(
        select(Assignment).where(
            Assignment.task_id == task.id,
            Assignment.volunteer_id == profile.id,
        )
    )
    if existing is None:
        db.add(Assignment(task_id=task.id, volunteer_id=profile.id, status="applied"))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()

    return RedirectResponse(
        f"/v/tasks/{task.id}?message=Application submitted.",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/assignments")
def assignments_page(request: Request, db: DbSession):
    user = require_volunteer(request, db)
    if isinstance(user, RedirectResponse):
        return user

    profile = get_or_create_profile(user, db)
    assignments = db.execute(
        select(Assignment, Task)
        .join(Task, Assignment.task_id == Task.id)
        .where(Assignment.volunteer_id == profile.id)
        .order_by(Assignment.applied_at.desc())
        .limit(settings.VOLUNTEER_ASSIGNMENTS_LIMIT)
    ).all()
    return templates.TemplateResponse(
        "volunteer/assignments.html",
        context(request, user, assignments=assignments),
    )
