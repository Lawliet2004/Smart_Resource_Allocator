"""Import every model here so Base.metadata sees it (required by Alembic autogenerate)."""

from app.models.task import Task  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.volunteer import Volunteer  # noqa: F401
