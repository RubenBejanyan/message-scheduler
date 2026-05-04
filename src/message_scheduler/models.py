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

    # "interval" → fires every N seconds; "cron" → fires on a cron expression
    interval_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # For interval: number of seconds as string. For cron: "HH:MM" (daily at time).
    interval_value: Mapped[str] = mapped_column(String(50), nullable=False)
    # Human-readable description stored for display
    interval_label: Mapped[str] = mapped_column(String(100), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    job_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
