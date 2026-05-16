from fastapi import Depends, FastAPI
from sqlalchemy import func, select

from ..admin import setup_admin
from ..database import async_session_factory
from ..models import RegisteredUser, ScheduledTask, SentMessage
from .deps import require_api_key
from .schedules import router as schedules_router
from .schemas import StatsOut
from .users import router as users_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="ChronoPost Admin API",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(
        "/api/stats",
        response_model=StatsOut,
        tags=["system"],
        dependencies=[Depends(require_api_key)],
    )
    async def stats() -> StatsOut:
        async with async_session_factory() as session:
            total_users = (
                await session.execute(select(func.count()).select_from(RegisteredUser))
            ).scalar() or 0
            approved_users = (
                await session.execute(
                    select(func.count())
                    .select_from(RegisteredUser)
                    .where(RegisteredUser.is_approved == True)  # noqa: E712
                )
            ).scalar() or 0
            total_schedules = (
                await session.execute(select(func.count()).select_from(ScheduledTask))
            ).scalar() or 0
            active_schedules = (
                await session.execute(
                    select(func.count())
                    .select_from(ScheduledTask)
                    .where(
                        ScheduledTask.is_active == True,  # noqa: E712
                        ScheduledTask.is_paused == False,  # noqa: E712
                    )
                )
            ).scalar() or 0
            paused_schedules = (
                await session.execute(
                    select(func.count())
                    .select_from(ScheduledTask)
                    .where(
                        ScheduledTask.is_active == True,  # noqa: E712
                        ScheduledTask.is_paused == True,  # noqa: E712
                    )
                )
            ).scalar() or 0
            messages_sent = (
                await session.execute(select(func.count()).select_from(SentMessage))
            ).scalar() or 0

        return StatsOut(
            total_users=total_users,
            approved_users=approved_users,
            total_schedules=total_schedules,
            active_schedules=active_schedules,
            paused_schedules=paused_schedules,
            messages_sent_total=messages_sent,
        )

    app.include_router(schedules_router)
    app.include_router(users_router)
    setup_admin(app)
    return app
