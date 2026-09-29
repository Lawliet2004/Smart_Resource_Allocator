"""Shared UI option lists.

``SKILL_OPTIONS`` lives in :mod:`app.services.skills` because it is domain data,
not presentation data; it is re-exported here for templates and form handlers.
"""

from app.services.skills import SKILL_OPTIONS

ROLE_OPTIONS: list[tuple[str, str]] = [
    ("volunteer", "Volunteer"),
    ("coordinator", "Coordinator"),
]

TASK_STATUSES = {"open", "pending", "closed", "completed", "cancelled"}
ASSIGNMENT_ACTIONS = {"approve", "reject", "complete"}

__all__ = ["ASSIGNMENT_ACTIONS", "ROLE_OPTIONS", "SKILL_OPTIONS", "TASK_STATUSES"]
