"""Add media_type and media_file_id to scheduled_tasks

Revision ID: 008
Revises: 007
Create Date: 2026-05-17
"""

import sqlalchemy as sa

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scheduled_tasks",
        sa.Column("media_type", sa.String(20), nullable=True),
    )
    op.add_column(
        "scheduled_tasks",
        sa.Column("media_file_id", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scheduled_tasks", "media_file_id")
    op.drop_column("scheduled_tasks", "media_type")
