"""Match volunteers to a task."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.task import Task
from app.models.volunteer import Volunteer
from app.services.scoring import is_eligible, match_score


def find_best_volunteers(
    task: Task, db: Session, limit: int | None = None
) -> list[Volunteer]:
    """Eligible available volunteers for a task, best match first.

    Eligibility and scoring are shared with the volunteer-facing task list (see
    :mod:`app.services.scoring`), so both sides of the app agree on what counts
    as a match.

    ``MATCHER_CANDIDATE_LIMIT`` bounds how many rows we pull into memory; the
    ranking and any caller-supplied ``limit`` are applied *after* filtering so a
    good match is never dropped just for having a low id.
    """
    stmt = (
        select(Volunteer)
        .where(Volunteer.is_available.is_(True))
        .order_by(Volunteer.id.desc())
        .limit(settings.MATCHER_CANDIDATE_LIMIT)
    )
    candidates = db.execute(stmt).scalars().all()

    matched = [volunteer for volunteer in candidates if is_eligible(task, volunteer)]
    matched.sort(key=lambda volunteer: (-match_score(task, volunteer), volunteer.id or 0))

    if limit is not None:
        return matched[:limit]
    return matched
