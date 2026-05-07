"""Add sent_messages table for message history.

Revision ID: 002
Revises: 001
Create Date: 2026-05-07
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sent_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("user_telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("target_username", sa.String(100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sent_messages_task_id", "sent_messages", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_sent_messages_task_id", table_name="sent_messages")
    op.drop_table("sent_messages")
