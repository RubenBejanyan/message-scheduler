from fastapi import FastAPI
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from .config import settings
from .database import engine
from .models import RegisteredUser, ScheduledTask, SentMessage


class _AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        password = str(form.get("password", ""))
        if not settings.api_key or password == settings.api_key:
            request.session["authenticated"] = True
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        if not settings.api_key:
            return True
        return bool(request.session.get("authenticated"))


class UserAdmin(ModelView, model=RegisteredUser):
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-users"
    can_create = False
    can_delete = False
    page_size = 50

    column_list = [
        RegisteredUser.telegram_id,
        RegisteredUser.first_name,
        RegisteredUser.username,
        RegisteredUser.is_approved,
        RegisteredUser.is_admin,
        RegisteredUser.created_at,
    ]
    column_searchable_list = [RegisteredUser.username, RegisteredUser.first_name]
    column_sortable_list = [
        RegisteredUser.created_at,
        RegisteredUser.is_approved,
        RegisteredUser.is_admin,
    ]
    column_default_sort = [(RegisteredUser.created_at, True)]
    form_columns = [RegisteredUser.is_approved, RegisteredUser.is_admin]


class ScheduleAdmin(ModelView, model=ScheduledTask):
    name = "Schedule"
    name_plural = "Schedules"
    icon = "fa-solid fa-calendar-days"
    can_create = False
    page_size = 50

    column_list = [
        ScheduledTask.id,
        ScheduledTask.user_telegram_id,
        ScheduledTask.target_username,
        ScheduledTask.interval_label,
        ScheduledTask.message_mode,
        ScheduledTask.language,
        ScheduledTask.is_active,
        ScheduledTask.is_paused,
        ScheduledTask.sent_count,
        ScheduledTask.repeat_count,
        ScheduledTask.consecutive_failures,
        ScheduledTask.last_sent_at,
        ScheduledTask.created_at,
    ]
    column_searchable_list = [ScheduledTask.target_username, ScheduledTask.topic]
    column_sortable_list = [
        ScheduledTask.id,
        ScheduledTask.created_at,
        ScheduledTask.last_sent_at,
        ScheduledTask.consecutive_failures,
        ScheduledTask.sent_count,
    ]
    column_default_sort = [(ScheduledTask.created_at, True)]
    form_columns = [ScheduledTask.is_active, ScheduledTask.is_paused]


class MessageAdmin(ModelView, model=SentMessage):
    name = "Sent Message"
    name_plural = "Sent Messages"
    icon = "fa-solid fa-paper-plane"
    can_create = False
    can_edit = False
    can_delete = False
    page_size = 50

    column_list = [
        SentMessage.id,
        SentMessage.task_id,
        SentMessage.target_username,
        SentMessage.content,
        SentMessage.sent_at,
    ]
    column_searchable_list = [SentMessage.target_username, SentMessage.content]
    column_sortable_list = [SentMessage.sent_at, SentMessage.task_id]
    column_default_sort = [(SentMessage.sent_at, True)]


def setup_admin(app: FastAPI) -> None:
    secret = settings.api_key or "chronopost-admin-dev-secret"
    auth_backend = _AdminAuth(secret_key=secret)
    admin = Admin(
        app,
        engine=engine,
        title="ChronoPost Admin",
        authentication_backend=auth_backend,
    )
    admin.add_view(UserAdmin)
    admin.add_view(ScheduleAdmin)
    admin.add_view(MessageAdmin)
