"""Add timezone column to scheduled_tasks.

Revision ID: 006
Revises: 005
Create Date: 2026-05-09
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scheduled_tasks",
        sa.Column("timezone", sa.String(50), nullable=False, server_default="UTC"),
    )


def downgrade() -> None:
    op.drop_column("scheduled_tasks", "timezone")
