"""enforce single org per coordinator

Revision ID: f4a1a9c2d18e
Revises: c8a73d17f0b2
Create Date: 2026-04-22 11:35:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f4a1a9c2d18e"
down_revision: Union[str, Sequence[str], None] = "c8a73d17f0b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Keep the oldest organization linked to each coordinator and detach duplicates.
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    created_by_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY created_by_id
                        ORDER BY id ASC
                    ) AS row_num
                FROM organizations
                WHERE created_by_id IS NOT NULL
            )
            UPDATE organizations AS o
            SET created_by_id = NULL
            FROM ranked AS r
            WHERE o.id = r.id AND r.row_num > 1
            """
        )
    )

    bind = op.get_bind()
    constraint_exists = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'uq_organizations_created_by_id'
            """
        )
    ).scalar()
    if not constraint_exists:
        op.create_unique_constraint(
            "uq_organizations_created_by_id",
            "organizations",
            ["created_by_id"],
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        sa.text(
            "ALTER TABLE organizations DROP CONSTRAINT IF EXISTS uq_organizations_created_by_id"
        )
    )
