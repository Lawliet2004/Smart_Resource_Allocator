"""Task capacity helpers shared by volunteer and coordinator flows."""

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.assignment import Assignment
from app.models.task import Task

FILLING_ASSIGNMENT_STATUSES = ("approved", "completed")


def task_capacity(task: Task) -> int:
    return max(1, task.people_needed or 1)


def filled_slots_by_task_ids(db: Session, task_ids: Iterable[int | None]) -> dict[int, int]:
    ids = {task_id for task_id in task_ids if task_id is not None}
    if not ids:
        return {}

    rows = db.execute(
        select(Assignment.task_id, func.count(Assignment.id))
        .where(
            Assignment.task_id.in_(ids),
            Assignment.status.in_(FILLING_ASSIGNMENT_STATUSES),
        )
        .group_by(Assignment.task_id)
    ).all()
    return {task_id: count for task_id, count in rows}


def filled_slots_for_task(db: Session, task_id: int) -> int:
    return filled_slots_by_task_ids(db, [task_id]).get(task_id, 0)


def capacity_summary(task: Task, filled_slots: int) -> dict[str, int | bool]:
    needed = task_capacity(task)
    filled = min(filled_slots, needed)
    remaining = max(needed - filled_slots, 0)
    return {
        "needed": needed,
        "filled": filled,
        "remaining": remaining,
        "is_full": remaining == 0,
    }


def capacity_summaries(tasks: Iterable[Task], db: Session) -> dict[int, dict[str, int | bool]]:
    task_list = list(tasks)
    filled_by_task_id = filled_slots_by_task_ids(db, [task.id for task in task_list])
    return {
        task.id: capacity_summary(task, filled_by_task_id.get(task.id, 0))
        for task in task_list
        if task.id is not None
    }
