"""Add index on scheduled_tasks.user_telegram_id.

Revision ID: 004
Revises: 003
Create Date: 2026-05-07
"""
from collections.abc import Sequence

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_scheduled_tasks_user_telegram_id",
        "scheduled_tasks",
        ["user_telegram_id"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_scheduled_tasks_user_telegram_id", table_name="scheduled_tasks")
