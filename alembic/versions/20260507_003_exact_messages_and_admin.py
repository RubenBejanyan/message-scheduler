"""Add exact message mode and admin delegation.

Revision ID: 003
Revises: 002
Create Date: 2026-05-07
"""
from collections.abc import Sequence

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS "
        "message_mode VARCHAR(10) NOT NULL DEFAULT 'ai'"
    )
    op.execute(
        "ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS messages_json TEXT"
    )
    op.execute(
        "ALTER TABLE registered_users ADD COLUMN IF NOT EXISTS "
        "is_admin BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    op.drop_column("scheduled_tasks", "message_mode")
    op.drop_column("scheduled_tasks", "messages_json")
    op.drop_column("registered_users", "is_admin")
