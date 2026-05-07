"""Add FK constraint from sent_messages.task_id to scheduled_tasks.id.

Revision ID: 005
Revises: 004
Create Date: 2026-05-08
"""
from collections.abc import Sequence

from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_sent_messages_task_id",
        "sent_messages",
        "scheduled_tasks",
        ["task_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_sent_messages_task_id", "sent_messages", type_="foreignkey")
