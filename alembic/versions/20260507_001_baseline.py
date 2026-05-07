"""Baseline schema — all tables and columns up to this point.

Uses IF NOT EXISTS throughout so it is safe to run against existing databases
that were created by the previous SQLAlchemy create_all + raw-SQL migration
approach.

Revision ID: 001
Revises:
Create Date: 2026-05-07
"""
from typing import Sequence, Union

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS registered_users (
            telegram_id BIGINT PRIMARY KEY,
            username    VARCHAR(100),
            first_name  VARCHAR(100) NOT NULL,
            is_approved BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id               SERIAL PRIMARY KEY,
            target_username  VARCHAR(100) NOT NULL,
            topic            TEXT NOT NULL,
            interval_type    VARCHAR(20) NOT NULL,
            interval_value   VARCHAR(50) NOT NULL,
            interval_label   VARCHAR(150) NOT NULL,
            is_active        BOOLEAN NOT NULL DEFAULT TRUE,
            job_id           VARCHAR(100) UNIQUE NOT NULL,
            created_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            last_sent_at     TIMESTAMP WITH TIME ZONE
        )
    """)

    # Columns added incrementally after initial release
    op.execute("ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS jitter_seconds INTEGER")
    op.execute(
        "ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS "
        "language VARCHAR(50) NOT NULL DEFAULT 'English'"
    )
    op.execute("ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS user_telegram_id BIGINT")
    op.execute(
        "ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS "
        "send_as VARCHAR(10) NOT NULL DEFAULT 'bot'"
    )
    op.execute(
        "ALTER TABLE registered_users ADD COLUMN IF NOT EXISTS "
        "has_telethon_session BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS "
        "consecutive_failures INTEGER NOT NULL DEFAULT 0"
    )
    op.execute("ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS last_error TEXT")
    op.execute(
        "ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS "
        "is_paused BOOLEAN NOT NULL DEFAULT FALSE"
    )

    # Auto-approve any users left in pending state from old approval flow
    op.execute("UPDATE registered_users SET is_approved = TRUE WHERE is_approved = FALSE")


def downgrade() -> None:
    pass  # intentionally irreversible baseline
