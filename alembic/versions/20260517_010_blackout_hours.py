"""Add blackout_start and blackout_end to scheduled_tasks

Revision ID: 010
Revises: 009
Create Date: 2026-05-17
"""

import sqlalchemy as sa

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scheduled_tasks",
        sa.Column("blackout_start", sa.String(5), nullable=True),
    )
    op.add_column(
        "scheduled_tasks",
        sa.Column("blackout_end", sa.String(5), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scheduled_tasks", "blackout_end")
    op.drop_column("scheduled_tasks", "blackout_start")
