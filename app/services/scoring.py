"""Task/volunteer matching rules.

Both directions of matching — "which tasks suit this volunteer" (volunteer
dashboard) and "which volunteers suit this task" (coordinator ingest) — use the
same eligibility check and the same score, so the two views can never disagree
about who matches what.
"""

from app.models.task import Task
from app.models.volunteer import Volunteer
from app.services.skills import normalized_skill_set

# The extractor emits this sentinel when it cannot find a location in a field
# report. Such tasks are treated as "anywhere" rather than as a literal place.
UNKNOWN_LOCATION = "unknown"

SKILL_OVERLAP_POINTS = 25
LOCATION_MATCH_POINTS = 30
AVAILABILITY_POINTS = 20
URGENCY_POINTS = 5


def _normalized_location(value: str | None) -> str:
    return (value or "").strip().casefold()


def task_requires_location(task: Task) -> bool:
    location = _normalized_location(task.location)
    return bool(location) and location != UNKNOWN_LOCATION


def is_eligible(task: Task, volunteer: Volunteer) -> bool:
    """Whether a volunteer may be matched to a task at all.

    A task with a concrete location only matches volunteers in that location; a
    task with required skills only matches volunteers sharing at least one.
    """
    if task_requires_location(task):
        if _normalized_location(task.location) != _normalized_location(volunteer.location):
            return False

    required_skills = normalized_skill_set(task.required_skills)
    if required_skills and not required_skills & normalized_skill_set(volunteer.skills):
        return False

    return True


def match_score(task: Task, volunteer: Volunteer) -> int:
    """Higher is a better match. Roughly 0-100 for realistic inputs."""
    score = 0

    required_skills = normalized_skill_set(task.required_skills)
    if required_skills:
        overlap = required_skills & normalized_skill_set(volunteer.skills)
        score += len(overlap) * SKILL_OVERLAP_POINTS

    task_location = _normalized_location(task.location)
    volunteer_location = _normalized_location(volunteer.location)
    if task_location and volunteer_location and task_location == volunteer_location:
        score += LOCATION_MATCH_POINTS

    if volunteer.is_available:
        score += AVAILABILITY_POINTS

    score += max(1, min(task.urgency or 1, 5)) * URGENCY_POINTS
    return score
