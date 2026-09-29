"""Volunteer-facing pages."""

from fastapi import APIRouter, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models.assignment import Assignment
from app.models.task import Task
from app.models.user import User
from app.models.volunteer import Volunteer
from app.services.capacity import (
    capacity_summaries,
    capacity_summary,
    filled_slots_for_task,
    lock_task_for_update,
)
from app.services.scoring import is_eligible, match_score
from app.services.search import LIKE_ESCAPE_CHAR, like_pattern
from app.services.skills import SKILL_OPTIONS, VALID_SKILLS, normalize_skills
from app.web.deps import DbSession, get_current_user, login_path
from app.web.forms import (
    form_bool,
    form_float,
    form_list,
    form_value,
    parse_urlencoded_form,
)
from app.web.templates import context, templates

router = APIRouter()

MAX_NAME_CHARS = 255
MAX_PHONE_CHARS = 50
MAX_LOCATION_CHARS = 255
MAX_TASK_SEARCH_CHARS = 100


def parse_urgency_filter(value: str) -> int | None:
    if not value:
        return None
    try:
        urgency = int(value)
    except ValueError:
        return None
    if 1 <= urgency <= 5:
        return urgency
    return None


def clamp_search(value: str) -> str:
    return value[:MAX_TASK_SEARCH_CHARS]


def volunteer_task_filters(request: Request) -> dict[str, str | int | None]:
    query = request.query_params.get("q", "").strip()
    skill = request.query_params.get("skill", "").strip()
    location = request.query_params.get("location", "").strip()
    urgency = request.query_params.get("urgency", "").strip()
    if skill and skill not in VALID_SKILLS:
        skill = ""
    parsed_urgency = parse_urgency_filter(urgency)
    return {
        "q": query,
        "skill": skill,
        "location": location,
        "urgency": parsed_urgency,
    }


def filter_matched_tasks(
    matched_tasks: list[tuple[Task, int]],
    filters: dict[str, str | int | None],
) -> list[tuple[Task, int]]:
    skill = str(filters.get("skill") or "")
    location = str(filters.get("location") or "").casefold()
    urgency = filters.get("urgency")
    filtered: list[tuple[Task, int]] = []
    for task, score in matched_tasks:
        if skill and skill not in (task.required_skills or []):
            continue
        if location and location not in (task.location or "").casefold():
            continue
        if isinstance(urgency, int) and (task.urgency or 1) < urgency:
            continue
        filtered.append((task, score))
    return filtered


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


def matched_open_tasks(
    db: DbSession, volunteer: Volunteer, q: str | None = None
) -> list[tuple[Task, int]]:
    """Open tasks this volunteer is eligible for, best match first.

    The free-text search runs in SQL over title *and* description so the
    dashboard quick-search and the full task list agree on what "matches".
    """
    stmt = select(Task).where(Task.status.in_(["open", "pending"]))

    search = (q or "").strip()
    if search:
        pattern = like_pattern(clamp_search(search))
        stmt = stmt.where(
            or_(
                Task.title.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
                Task.description.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
            )
        )

    stmt = stmt.order_by(Task.urgency.desc(), Task.id.desc()).limit(
        settings.VOLUNTEER_TASK_SCAN_LIMIT
    )
    tasks = db.execute(stmt).scalars().all()

    capacity_by_task_id = capacity_summaries(tasks, db)
    ranked: list[tuple[Task, int]] = []
    for task in tasks:
        capacity = capacity_by_task_id.get(task.id)
        if capacity is not None and capacity["is_full"]:
            continue
        if not is_eligible(task, volunteer):
            continue
        ranked.append((task, match_score(task, volunteer)))
    return sorted(ranked, key=lambda item: (-item[1], -(item[0].id or 0)))


@router.get("/")
def dashboard(request: Request, db: DbSession, q: str | None = None):
    user = require_volunteer(request, db)
    if isinstance(user, RedirectResponse):
        return user

    profile = get_or_create_profile(user, db)
    search = clamp_search((q or "").strip())
    matched_tasks = matched_open_tasks(db, profile, q=search)[:5]
    capacity_by_task_id = capacity_summaries((task for task, _score in matched_tasks), db)

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            "partials/matched_tasks_list.html",
            context(
                request,
                user,
                matched_tasks=matched_tasks,
                capacity_by_task_id=capacity_by_task_id,
                search=search,
            ),
        )

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
            matched_tasks=matched_tasks,
            capacity_by_task_id=capacity_by_task_id,
            assignments=assignments,
            assignment_count=assignment_count,
            search=search,
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
    filters = volunteer_task_filters(request)
    if len(str(filters["q"] or "")) > MAX_TASK_SEARCH_CHARS:
        return RedirectResponse(
            "/v/tasks?error=Search is too long.", status_code=status.HTTP_303_SEE_OTHER
        )
    if len(str(filters["location"] or "")) > MAX_LOCATION_CHARS:
        return RedirectResponse(
            "/v/tasks?error=Location filter is too long.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    matched_tasks = filter_matched_tasks(
        matched_open_tasks(db, profile, q=str(filters["q"] or "")), filters
    )
    return templates.TemplateResponse(
        "volunteer/tasks.html",
        context(
            request,
            user,
            profile=profile,
            matched_tasks=matched_tasks,
            capacity_by_task_id=capacity_summaries((task for task, _score in matched_tasks), db),
            filters=filters,
            skills=SKILL_OPTIONS,
        ),
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

    capacity = capacity_summary(task, filled_slots_for_task(db, task.id))
    return templates.TemplateResponse(
        "volunteer/task_detail.html",
        context(
            request,
            user,
            task=task,
            profile=profile,
            assignment=assignment,
            capacity=capacity,
        ),
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
    if existing is not None:
        return RedirectResponse(
            f"/v/tasks/{task.id}?message=Application already submitted.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Lock the task row so the capacity check below cannot race another
    # application or an approval happening at the same moment.
    locked_task = lock_task_for_update(db, task.id)
    if locked_task is None:
        db.rollback()
        return RedirectResponse(
            "/v/tasks?error=Task not found.", status_code=status.HTTP_303_SEE_OTHER
        )

    capacity = capacity_summary(locked_task, filled_slots_for_task(db, locked_task.id))
    if capacity["is_full"]:
        db.rollback()
        return RedirectResponse(
            f"/v/tasks/{task.id}?error=Task already has enough approved volunteers.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    db.add(Assignment(task_id=task.id, volunteer_id=profile.id, status="applied"))
    try:
        db.commit()
    except IntegrityError:
        # The unique (task_id, volunteer_id) constraint fired: someone
        # double-submitted. Report the truth rather than a phantom success.
        db.rollback()
        return RedirectResponse(
            f"/v/tasks/{task.id}?message=Application already submitted.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

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
