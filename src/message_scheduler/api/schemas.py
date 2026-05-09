from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_telegram_id: int
    target_username: str
    topic: str
    interval_type: str
    interval_value: str
    interval_label: str
    jitter_seconds: int | None
    language: str
    timezone: str
    is_active: bool
    is_paused: bool
    message_mode: str
    messages_json: str | None
    consecutive_failures: int
    last_error: str | None
    created_at: datetime
    last_sent_at: datetime | None
    next_run_at: datetime | None = None
    job_id: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    telegram_id: int
    username: str | None
    first_name: str
    is_approved: bool
    is_admin: bool
    created_at: datetime


class SentMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    target_username: str
    content: str
    sent_at: datetime


class StatsOut(BaseModel):
    total_users: int
    approved_users: int
    total_schedules: int
    active_schedules: int
    paused_schedules: int
    messages_sent_total: int
