"""Add repeat_count and sent_count to scheduled_tasks.

Revision ID: 007
Revises: 006
Create Date: 2026-05-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scheduled_tasks", sa.Column("repeat_count", sa.Integer(), nullable=True))
    op.add_column(
        "scheduled_tasks",
        sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("scheduled_tasks", "sent_count")
    op.drop_column("scheduled_tasks", "repeat_count")
