"""Add extra_targets to scheduled_tasks

Revision ID: 009
Revises: 008
Create Date: 2026-05-17
"""

import sqlalchemy as sa

from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scheduled_tasks",
        sa.Column("extra_targets", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scheduled_tasks", "extra_targets")
