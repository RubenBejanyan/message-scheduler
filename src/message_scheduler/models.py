from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class ScheduledTask(Base):
    """Represents one recurring scheduled message."""

    __tablename__ = "scheduled_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
