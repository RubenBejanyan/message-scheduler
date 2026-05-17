from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class RegisteredUser(Base):
    """A Telegram user who has been granted access to the bot."""

    __tablename__ = "registered_users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="FALSE"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ScheduledTask(Base):
    """Represents one recurring scheduled message."""

    __tablename__ = "scheduled_tasks"

    __table_args__ = (Index("ix_scheduled_tasks_user_telegram_id", "user_telegram_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_username: Mapped[str] = mapped_column(String(100), nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)

    # "interval" → fires every N seconds; "cron" → fires daily at HH:MM;
    # "window" → fires daily at random time between HH:MM and HH:MM
    interval_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # interval: seconds as string | cron: "HH:MM" | window: "HH:MM-HH:MM"
    interval_value: Mapped[str] = mapped_column(String(50), nullable=False)
    interval_label: Mapped[str] = mapped_column(String(150), nullable=False)

    # Extra random delay added on top of scheduled time (0–jitter_seconds).
    # None / 0 means no jitter. Not used for window type (window IS the randomization).
    jitter_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)

    language: Mapped[str] = mapped_column(
        String(50), nullable=False, default="English", server_default="English"
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    job_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    is_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # "ai" → generate via LLM; "exact" → pick randomly from messages_json list
    message_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="ai", server_default="ai"
    )
    # JSON array of strings, used only when message_mode == "exact"
    messages_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # IANA timezone name, e.g. "UTC", "Europe/Moscow". Relevant only for cron/window types.
    timezone: Mapped[str] = mapped_column(
        String(50), nullable=False, default="UTC", server_default="UTC"
    )

    # "photo" | "voice" | "document" | "video" | "animation" | None (text)
    media_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Telegram file_id for the media to send; only set when media_type is not None.
    media_file_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # JSON list of additional target strings beyond the primary target_username.
    # e.g. '["@chan2", "-1009876543"]'
    extra_targets: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Quiet-hours window: skip sends when local time falls in [blackout_start, blackout_end).
    # Stored as "HH:MM". Overnight windows (e.g. 23:00–08:00) are supported.
    blackout_start: Mapped[str | None] = mapped_column(String(5), nullable=True)
    blackout_end: Mapped[str | None] = mapped_column(String(5), nullable=True)

    # Optional cap on total sends. None = unlimited.
    repeat_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Total number of successful sends so far.
    sent_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SentMessage(Base):
    """A record of one AI-generated message that was successfully delivered."""

    __tablename__ = "sent_messages"
    __table_args__ = (Index("ix_sent_messages_task_id", "task_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scheduled_tasks.id", ondelete="CASCADE"), nullable=False
    )
    user_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    target_username: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
