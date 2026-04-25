"""Coordinator-facing pages."""

import logging
from collections import Counter
from datetime import UTC, datetime

from fastapi import APIRouter, Request, status
from fastapi.responses import RedirectResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import settings
from app.models.assignment import Assignment
from app.models.organization import Organization
from app.models.task import Task
from app.models.user import User
from app.models.volunteer import Volunteer
from app.services.capacity import capacity_summaries, capacity_summary, filled_slots_for_task
from app.services.extractor import extract_task_data
from app.services.matcher import find_best_volunteers
from app.web.deps import DbSession, get_current_user, login_path
from app.web.forms import (
    form_float,
    form_list,
    form_value,
    parse_urlencoded_form,
)
from app.web.options import ASSIGNMENT_ACTIONS, SKILL_OPTIONS, TASK_STATUSES
from app.web.templates import context, templates

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_SKILLS = {value for value, _label in SKILL_OPTIONS}
MAX_LOCATION_CHARS = 255


def normalize_skills(skills: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for skill in skills:
        if skill in VALID_SKILLS and skill not in seen:
            deduped.append(skill)
            seen.add(skill)
    return deduped


def parse_urgency(value: str) -> int | None:
    try:
        urgency = int(value)
    except ValueError:
        return None
    if 1 <= urgency <= 5:
        return urgency
    return None


def parse_people_needed(value: str) -> int | None:
    try:
        people_needed = int(value)
    except ValueError:
        return None
    if people_needed >= 1:
        return people_needed
    return None


def parse_title(value: str) -> str | None:
    title = value.strip()
    if not title or len(title) > settings.TASK_TITLE_MAX_CHARS:
        return None
    return title


def require_coordinator(request: Request, db: DbSession) -> User | RedirectResponse:
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(
            login_path(str(request.url.path)), status_code=status.HTTP_303_SEE_OTHER
        )
    if user.role != "coordinator":
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return user


def get_or_create_organization(user: User, db: DbSession) -> Organization:
    organization = db.scalar(select(Organization).where(Organization.created_by_id == user.id))
    if organization is not None:
        return organization

    organization = Organization(name="My NGO", created_by_id=user.id)
    try:
        db.add(organization)
        db.commit()
        db.refresh(organization)
        return organization
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Organization).where(Organization.created_by_id == user.id))
        if existing is not None:
            return existing
        raise


def coordinator_task_query(user: User, org: Organization):
    return select(Task).where((Task.created_by_id == user.id) | (Task.org_id == org.id))


def owned_task(task_id: int, user: User, org: Organization, db: DbSession) -> Task | None:
    return db.scalar(coordinator_task_query(user, org).where(Task.id == task_id))


def percentage(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return round((numerator / denominator) * 100)


def coordinator_analytics(user: User, org: Organization, db: DbSession) -> dict[str, object]:
    ownership_filter = (Task.created_by_id == user.id) | (Task.org_id == org.id)

    task_status_counts = {
        status_value: count
        for status_value, count in db.execute(
            select(Task.status, func.count(Task.id)).where(ownership_filter).group_by(Task.status)
        ).all()
    }
    assignment_status_counts = {
        status_value: count
        for status_value, count in db.execute(
            select(Assignment.status, func.count(Assignment.id))
            .join(Task, Assignment.task_id == Task.id)
            .where(ownership_filter)
            .group_by(Assignment.status)
        ).all()
    }

    total_tasks = sum(task_status_counts.values())
    total_applications = sum(assignment_status_counts.values())
    active_tasks = task_status_counts.get("open", 0) + task_status_counts.get("pending", 0)
    completed_tasks = task_status_counts.get("completed", 0)
    archived_tasks = task_status_counts.get("closed", 0) + task_status_counts.get("cancelled", 0)
    pending_applications = assignment_status_counts.get("applied", 0)
    approved_assignments = assignment_status_counts.get("approved", 0)
    rejected_assignments = assignment_status_counts.get("rejected", 0)
    completed_assignments = assignment_status_counts.get("completed", 0)
    filled_tasks = db.scalar(
        select(func.count(func.distinct(Assignment.task_id)))
        .join(Task, Assignment.task_id == Task.id)
        .where(ownership_filter, Assignment.status.in_(["approved", "completed"]))
    ) or 0

    skill_counts: Counter[str] = Counter()
    for (skills,) in db.execute(select(Task.required_skills).where(ownership_filter)).all():
        for skill in skills or []:
            if isinstance(skill, str):
                skill_counts[skill] += 1

    top_skills = [
        {"skill": skill, "count": count}
        for skill, count in sorted(
            skill_counts.items(), key=lambda item: (-item[1], item[0])
        )[:5]
    ]
    if total_tasks:
        avg_applications_per_task = f"{(total_applications / total_tasks):.1f}"
    else:
        avg_applications_per_task = "0.0"

    return {
        "total_tasks": total_tasks,
        "active_tasks": active_tasks,
        "completed_tasks": completed_tasks,
        "archived_tasks": archived_tasks,
        "total_applications": total_applications,
        "pending_applications": pending_applications,
        "approved_assignments": approved_assignments,
        "rejected_assignments": rejected_assignments,
        "completed_assignments": completed_assignments,
        "fill_rate": percentage(filled_tasks, total_tasks),
        "completion_rate": percentage(completed_tasks, total_tasks),
        "avg_applications_per_task": avg_applications_per_task,
        "task_status_rows": [
            {
                "label": label,
                "count": task_status_counts.get(status_value, 0),
                "percent": percentage(task_status_counts.get(status_value, 0), total_tasks),
            }
            for status_value, label in [
                ("open", "Open"),
                ("pending", "Pending"),
                ("completed", "Completed"),
                ("closed", "Closed"),
                ("cancelled", "Cancelled"),
            ]
        ],
        "application_status_rows": [
            {
                "label": label,
                "count": assignment_status_counts.get(status_value, 0),
                "percent": percentage(
                    assignment_status_counts.get(status_value, 0), total_applications
                ),
            }
            for status_value, label in [
                ("applied", "Pending"),
                ("approved", "Approved"),
                ("rejected", "Rejected"),
                ("completed", "Completed"),
            ]
        ],
        "top_skills": top_skills,
    }


@router.get("/")
def dashboard(request: Request, db: DbSession):
    user = require_coordinator(request, db)
    if isinstance(user, RedirectResponse):
        return user

    org = get_or_create_organization(user, db)
    ownership_filter = (Task.created_by_id == user.id) | (Task.org_id == org.id)
    tasks = db.execute(
        coordinator_task_query(user, org)
        .where(Task.status != "closed")
        .order_by(Task.id.desc())
        .limit(settings.COORDINATOR_TASK_LIMIT)
    ).scalars().all()
    pending_applications = db.execute(
        select(Assignment, Task, Volunteer)
        .join(Task, Assignment.task_id == Task.id)
        .join(Volunteer, Assignment.volunteer_id == Volunteer.id)
        .where(
            ownership_filter,
            Assignment.status == "applied",
        )
        .order_by(Assignment.applied_at.desc())
        .limit(settings.COORDINATOR_PENDING_LIMIT)
    ).all()
    capacity_by_task_id = capacity_summaries(
        [*tasks, *(task for _assignment, task, _volunteer in pending_applications)],
        db,
    )

    return templates.TemplateResponse(
        "coordinator/dashboard.html",
        context(
            request,
            user,
            organization=org,
            tasks=tasks,
            pending_applications=pending_applications,
            capacity_by_task_id=capacity_by_task_id,
            analytics=coordinator_analytics(user, org, db),
        ),
    )


@router.get("/tasks/new")
def new_task_page(request: Request, db: DbSession):
    user = require_coordinator(request, db)
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse(
        "coordinator/task_form.html",
        context(request, user, task=None, skills=SKILL_OPTIONS, action="/c/tasks/new"),
    )


@router.post("/tasks/new")
async def create_task(request: Request, db: DbSession):
    user = require_coordinator(request, db)
    if isinstance(user, RedirectResponse):
        return user

    org = get_or_create_organization(user, db)
    form = await parse_urlencoded_form(request)
    title = parse_title(form_value(form, "title"))
    if title is None:
        return RedirectResponse(
            "/c/tasks/new?error=Task title is required and must be 255 characters or fewer.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    urgency = parse_urgency(form_value(form, "urgency", "1"))
    if urgency is None:
        return RedirectResponse(
            "/c/tasks/new?error=Urgency must be between 1 and 5.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    people_needed = parse_people_needed(form_value(form, "people_needed", "1"))
    if people_needed is None:
        return RedirectResponse(
            "/c/tasks/new?error=People needed must be at least 1.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    location = form_value(form, "location")
    if len(location) > MAX_LOCATION_CHARS:
        return RedirectResponse(
            "/c/tasks/new?error=Location must be 255 characters or fewer.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    task = Task(
        org_id=org.id,
        created_by_id=user.id,
        title=title,
        description=form_value(form, "description") or None,
        location=location or None,
        latitude=form_float(form, "latitude", min_value=-90, max_value=90),
        longitude=form_float(form, "longitude", min_value=-180, max_value=180),
        urgency=urgency,
        people_needed=people_needed,
        required_skills=normalize_skills(form_list(form, "required_skills")),
        status="open",
    )
    db.add(task)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        return RedirectResponse(
            "/c/?error=Unable to create task.",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        "/c/?message=Task created.",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/tasks/{task_id}/edit")
def edit_task_page(task_id: int, request: Request, db: DbSession):
    user = require_coordinator(request, db)
    if isinstance(user, RedirectResponse):
        return user

    org = get_or_create_organization(user, db)
    task = owned_task(task_id, user, org, db)
    if task is None:
        return RedirectResponse("/c/?error=Task not found.", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        "coordinator/task_form.html",
        context(request, user, task=task, skills=SKILL_OPTIONS, action=f"/c/tasks/{task.id}/edit"),
    )


@router.post("/tasks/{task_id}/edit")
async def update_task(task_id: int, request: Request, db: DbSession):
    user = require_coordinator(request, db)
    if isinstance(user, RedirectResponse):
        return user

    org = get_or_create_organization(user, db)
    task = owned_task(task_id, user, org, db)
    if task is None:
        return RedirectResponse("/c/?error=Task not found.", status_code=status.HTTP_303_SEE_OTHER)

    form = await parse_urlencoded_form(request)
    title = parse_title(form_value(form, "title"))
    if title is None:
        error_message = "Task title is required and must be 255 characters or fewer."
        return RedirectResponse(
            f"/c/tasks/{task.id}/edit?error={error_message}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    urgency = parse_urgency(form_value(form, "urgency", str(task.urgency or 1)))
    if urgency is None:
        return RedirectResponse(
            f"/c/tasks/{task.id}/edit?error=Urgency must be between 1 and 5.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    people_needed_val = str(task.people_needed or 1)
    people_needed = parse_people_needed(form_value(form, "people_needed", people_needed_val))
    if people_needed is None:
        return RedirectResponse(
            f"/c/tasks/{task.id}/edit?error=People needed must be at least 1.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    location = form_value(form, "location")
    if len(location) > MAX_LOCATION_CHARS:
        return RedirectResponse(
            f"/c/tasks/{task.id}/edit?error=Location must be 255 characters or fewer.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    task.title = title
    task.description = form_value(form, "description") or None
    task.location = location or None
    task.latitude = form_float(form, "latitude", min_value=-90, max_value=90)
    task.longitude = form_float(form, "longitude", min_value=-180, max_value=180)
    task.urgency = urgency
    task.people_needed = people_needed
    task.required_skills = normalize_skills(form_list(form, "required_skills"))
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        return RedirectResponse(
            f"/c/tasks/{task.id}/edit?error=Unable to update task.",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        "/c/?message=Task updated.",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/tasks/{task_id}/status")
async def update_task_status(task_id: int, request: Request, db: DbSession):
    user = require_coordinator(request, db)
    if isinstance(user, RedirectResponse):
        return user

    org = get_or_create_organization(user, db)
    task = owned_task(task_id, user, org, db)
    if task is None:
        return RedirectResponse("/c/?error=Task not found.", status_code=status.HTTP_303_SEE_OTHER)

    form = await parse_urlencoded_form(request)
    next_status = form_value(form, "status")
    if next_status not in TASK_STATUSES:
        return RedirectResponse(
            "/c/?error=Invalid task status.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    task.status = next_status
    db.commit()
    return RedirectResponse(
        "/c/?message=Task status updated.", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/tasks/{task_id}/applicants")
def applicants_page(task_id: int, request: Request, db: DbSession):
    user = require_coordinator(request, db)
    if isinstance(user, RedirectResponse):
        return user

    org = get_or_create_organization(user, db)
    task = owned_task(task_id, user, org, db)
    if task is None:
        return RedirectResponse("/c/?error=Task not found.", status_code=status.HTTP_303_SEE_OTHER)

    applications = db.execute(
        select(Assignment, Volunteer)
        .join(Volunteer, Assignment.volunteer_id == Volunteer.id)
        .where(Assignment.task_id == task.id)
        .order_by(Assignment.applied_at.desc())
        .limit(settings.APPLICANTS_LIMIT)
    ).all()
    capacity = capacity_summary(task, filled_slots_for_task(db, task.id))
    return templates.TemplateResponse(
        "coordinator/applicants.html",
        context(request, user, task=task, applications=applications, capacity=capacity),
    )


@router.post("/assignments/{assignment_id}/{action}")
def decide_assignment(assignment_id: int, action: str, request: Request, db: DbSession):
    user = require_coordinator(request, db)
    if isinstance(user, RedirectResponse):
        return user

    if action not in ASSIGNMENT_ACTIONS:
        return RedirectResponse("/c/?error=Invalid action.", status_code=status.HTTP_303_SEE_OTHER)

    org = get_or_create_organization(user, db)
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        return RedirectResponse(
            "/c/?error=Application not found.", status_code=status.HTTP_303_SEE_OTHER
        )

    task = owned_task(assignment.task_id, user, org, db)
    if task is None:
        return RedirectResponse(
            "/c/?error=Application not found.", status_code=status.HTTP_303_SEE_OTHER
        )

    now = datetime.now(UTC)
    if action == "approve":
        if assignment.status != "applied":
            return RedirectResponse(
                f"/c/tasks/{task.id}/applicants?error=Only applied assignments can be approved.",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        capacity = capacity_summary(task, filled_slots_for_task(db, task.id))
        if capacity["is_full"]:
            return RedirectResponse(
                f"/c/tasks/{task.id}/applicants?error=Task already has enough approved volunteers.",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        assignment.status = "approved"
        assignment.decided_at = now
        assignment.decided_by_id = user.id
    elif action == "reject":
        if assignment.status != "applied":
            return RedirectResponse(
                f"/c/tasks/{task.id}/applicants?error=Only applied assignments can be rejected.",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        assignment.status = "rejected"
        assignment.decided_at = now
        assignment.decided_by_id = user.id
    elif action == "complete":
        if assignment.status != "approved":
            return RedirectResponse(
                f"/c/tasks/{task.id}/applicants?error=Only approved assignments can be completed.",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        assignment.status = "completed"
        assignment.completed_at = now

    db.commit()
    return RedirectResponse(
        f"/c/tasks/{task.id}/applicants?message=Application updated.",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/ingest")
def ingest_page(request: Request, db: DbSession):
    user = require_coordinator(request, db)
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse("coordinator/ingest.html", context(request, user))


@router.post("/ingest")
async def ingest_report(request: Request, db: DbSession):
    user = require_coordinator(request, db)
    if isinstance(user, RedirectResponse):
        return user

    org = get_or_create_organization(user, db)
    form = await parse_urlencoded_form(request)
    is_hx_request = request.headers.get("HX-Request") == "true"

    raw_text = form_value(form, "raw_text")
    if not raw_text:
        template = "partials/ingest_result.html" if is_hx_request else "coordinator/ingest.html"
        return templates.TemplateResponse(
            template,
            context(request, user, error="Paste a field report first."),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if len(raw_text) > settings.MAX_INGEST_CHARS:
        template = "partials/ingest_result.html" if is_hx_request else "coordinator/ingest.html"
        return templates.TemplateResponse(
            template,
            context(
                request,
                user,
                error=f"Field report is too long (max {settings.MAX_INGEST_CHARS} characters).",
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        extracted = extract_task_data(raw_text)
        task = Task(
            org_id=org.id,
            created_by_id=user.id,
            raw_text=None,
            title=extracted["title"],
            description=extracted["description"],
            location=extracted["location"],
            urgency=extracted["urgency"],
            people_needed=extracted.get("people_needed", 1),
            required_skills=normalize_skills(extracted["required_skills"]),
            status="open",
        )
        db.add(task)
        db.flush()
        db.refresh(task)

        matched_volunteers = find_best_volunteers(task, db)
        db.commit()
    except RateLimitExceeded:
        # Let the rate-limit handler produce its own 429 response.
        raise
    except SQLAlchemyError:
        logger.exception("ingest_report failed with a database error")
        db.rollback()
        template = "partials/ingest_result.html" if is_hx_request else "coordinator/ingest.html"
        return templates.TemplateResponse(
            template,
            context(request, user, error="Unable to process field report right now."),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except Exception:
        # Any other unexpected failure (extractor bug, matcher bug, bad data) —
        # log it and show the same generic error so HTMX callers still get the
        # partial swap instead of a raw 500 body.
        logger.exception("ingest_report failed with an unexpected error")
        db.rollback()
        template = "partials/ingest_result.html" if is_hx_request else "coordinator/ingest.html"
        return templates.TemplateResponse(
            template,
            context(request, user, error="Unable to process field report right now."),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if not is_hx_request:
        return RedirectResponse(
            f"/c/tasks/{task.id}/edit?message=Task created from field report.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return templates.TemplateResponse(
        "partials/ingest_result.html",
        context(request, user, task=task, matched_volunteers=matched_volunteers),
    )
