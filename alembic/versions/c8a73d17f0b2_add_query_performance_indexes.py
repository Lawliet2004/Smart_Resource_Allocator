"""add query performance indexes

Revision ID: c8a73d17f0b2
Revises: 9c7f2a41d6b0
Create Date: 2026-04-22 01:10:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c8a73d17f0b2"
down_revision: Union[str, Sequence[str], None] = "9c7f2a41d6b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "ix_organizations_created_by_id",
        "organizations",
        ["created_by_id"],
        unique=False,
    )
    op.create_index("ix_tasks_org_id", "tasks", ["org_id"], unique=False)
    op.create_index("ix_tasks_created_by_id", "tasks", ["created_by_id"], unique=False)
    op.create_index("ix_tasks_status", "tasks", ["status"], unique=False)
    op.create_index("ix_volunteers_is_available", "volunteers", ["is_available"], unique=False)
    op.create_index(
        "ix_assignments_volunteer_id",
        "assignments",
        ["volunteer_id"],
        unique=False,
    )
    op.create_index("ix_assignments_status", "assignments", ["status"], unique=False)
    op.create_index("ix_assignments_applied_at", "assignments", ["applied_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_assignments_applied_at", table_name="assignments")
    op.drop_index("ix_assignments_status", table_name="assignments")
    op.drop_index("ix_assignments_volunteer_id", table_name="assignments")
    op.drop_index("ix_volunteers_is_available", table_name="volunteers")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_index("ix_tasks_created_by_id", table_name="tasks")
    op.drop_index("ix_tasks_org_id", table_name="tasks")
    op.drop_index("ix_organizations_created_by_id", table_name="organizations")
