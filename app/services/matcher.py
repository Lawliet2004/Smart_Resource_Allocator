from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.task import Task
from app.models.volunteer import Volunteer


def find_best_volunteers(task: Task, db: Session) -> list[Volunteer]:
    """
    Matches volunteers to a task based on skills and location.
    This is a basic matching engine.
    """
    # Fetch all available volunteers
    stmt = (
        select(Volunteer)
        .where(Volunteer.is_available.is_(True))
        .order_by(Volunteer.id.desc())
        .limit(settings.MATCHER_CANDIDATE_LIMIT)
    )
    volunteers = db.execute(stmt).scalars().all()

    matched = []
    task_location = (task.location or "").strip().casefold()
    required_skills = {
        skill.strip().casefold()
        for skill in (task.required_skills or [])
        if isinstance(skill, str) and skill.strip()
    }

    for vol in volunteers:
        # If task has a specific location, only match volunteers in that location
        volunteer_location = (vol.location or "").strip().casefold()
        if task_location and task_location != "unknown":
            if volunteer_location != task_location:
                continue

        # If task requires skills, check if volunteer has any
        if required_skills:
            volunteer_skills = {
                skill.strip().casefold()
                for skill in (vol.skills or [])
                if isinstance(skill, str) and skill.strip()
            }
            if not volunteer_skills.intersection(required_skills):
                continue

        matched.append(vol)

    return matched
