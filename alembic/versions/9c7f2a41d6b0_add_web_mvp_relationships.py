"""add web mvp relationships

Revision ID: 9c7f2a41d6b0
Revises: 2e83c318b506
Create Date: 2026-04-22 00:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9c7f2a41d6b0"
down_revision: Union[str, Sequence[str], None] = "2e83c318b506"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=100), nullable=True),
        sa.Column("contact", sa.String(length=100), nullable=True),
        sa.Column("area_of_operation", sa.String(length=255), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column("volunteers", sa.Column("user_id", sa.Integer(), nullable=True))
    op.add_column("volunteers", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("volunteers", sa.Column("longitude", sa.Float(), nullable=True))
    op.create_unique_constraint("uq_volunteers_user_id", "volunteers", ["user_id"])
    op.create_foreign_key(
        "fk_volunteers_user_id_users",
        "volunteers",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("tasks", sa.Column("org_id", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("created_by_id", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("tasks", sa.Column("longitude", sa.Float(), nullable=True))
    op.create_foreign_key(
        "fk_tasks_org_id_organizations",
        "tasks",
        "organizations",
        ["org_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_tasks_created_by_id_users",
        "tasks",
        "users",
        ["created_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("volunteer_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("role", sa.String(length=100), nullable=True),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_id", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["decided_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["volunteer_id"], ["volunteers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "volunteer_id", name="uq_assignment_task_volunteer"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("assignments")
    op.drop_constraint("fk_tasks_created_by_id_users", "tasks", type_="foreignkey")
    op.drop_constraint("fk_tasks_org_id_organizations", "tasks", type_="foreignkey")
    op.drop_column("tasks", "longitude")
    op.drop_column("tasks", "latitude")
    op.drop_column("tasks", "created_by_id")
    op.drop_column("tasks", "org_id")

    op.drop_constraint("fk_volunteers_user_id_users", "volunteers", type_="foreignkey")
    op.drop_constraint("uq_volunteers_user_id", "volunteers", type_="unique")
    op.drop_column("volunteers", "longitude")
    op.drop_column("volunteers", "latitude")
    op.drop_column("volunteers", "user_id")

    op.drop_table("organizations")
