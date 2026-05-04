from sqlalchemy import select

from .database import async_session_factory
from .models import RegisteredUser


async def get_user(telegram_id: int) -> RegisteredUser | None:
    async with async_session_factory() as session:
        return await session.get(RegisteredUser, telegram_id)


async def register_user(telegram_id: int, first_name: str, username: str | None) -> RegisteredUser:
    """Create auto-approved user record; returns existing record if already known."""
    async with async_session_factory() as session:
        user = await session.get(RegisteredUser, telegram_id)
        if user is None:
            user = RegisteredUser(
                telegram_id=telegram_id,
                first_name=first_name,
                username=username,
                is_approved=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user


async def set_session_status(telegram_id: int, has_session: bool) -> None:
    async with async_session_factory() as session:
        user = await session.get(RegisteredUser, telegram_id)
        if user is not None:
            user.has_telethon_session = has_session
            await session.commit()


async def block_user(telegram_id: int) -> bool:
    async with async_session_factory() as session:
        user = await session.get(RegisteredUser, telegram_id)
        if user is None:
            return False
        user.is_approved = False
        await session.commit()
        return True


async def unblock_user(telegram_id: int) -> bool:
    async with async_session_factory() as session:
        user = await session.get(RegisteredUser, telegram_id)
        if user is None:
            return False
        user.is_approved = True
        await session.commit()
        return True


async def list_active_users() -> list[RegisteredUser]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(RegisteredUser)
            .where(RegisteredUser.is_approved == True)  # noqa: E712
            .order_by(RegisteredUser.created_at)
        )
        return list(result.scalars().all())


async def list_blocked_users() -> list[RegisteredUser]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(RegisteredUser)
            .where(RegisteredUser.is_approved == False)  # noqa: E712
            .order_by(RegisteredUser.created_at)
        )
        return list(result.scalars().all())
