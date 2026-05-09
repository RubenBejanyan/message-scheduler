"""Integration tests for users CRUD — run against an in-memory SQLite DB."""

import pytest

from message_scheduler.users import (
    block_user,
    get_user,
    grant_admin,
    list_active_users,
    list_blocked_users,
    register_user,
    revoke_admin,
    unblock_user,
)

pytestmark = pytest.mark.usefixtures("patch_users_db")


async def test_register_user_creates_new() -> None:
    user = await register_user(111, "Alice", "alice")
    assert user.telegram_id == 111
    assert user.first_name == "Alice"
    assert user.username == "alice"
    assert user.is_approved is True
    assert user.is_admin is False


async def test_register_user_updates_existing() -> None:
    await register_user(222, "Bob", "bob")
    updated = await register_user(222, "Bobby", "bobby2")
    assert updated.first_name == "Bobby"
    assert updated.username == "bobby2"
    assert updated.telegram_id == 222


async def test_get_user_returns_existing() -> None:
    await register_user(333, "Carol", None)
    user = await get_user(333)
    assert user is not None
    assert user.telegram_id == 333
    assert user.username is None


async def test_get_user_returns_none_for_missing() -> None:
    user = await get_user(9999999)
    assert user is None


async def test_block_user_sets_approved_false() -> None:
    await register_user(444, "Dave", "dave")
    ok = await block_user(444)
    assert ok is True
    user = await get_user(444)
    assert user is not None
    assert user.is_approved is False


async def test_block_user_returns_false_for_missing() -> None:
    assert await block_user(9999998) is False


async def test_unblock_user_restores_approved() -> None:
    await register_user(555, "Eve", "eve")
    await block_user(555)
    ok = await unblock_user(555)
    assert ok is True
    user = await get_user(555)
    assert user is not None
    assert user.is_approved is True


async def test_unblock_user_returns_false_for_missing() -> None:
    assert await unblock_user(9999997) is False


async def test_grant_admin() -> None:
    await register_user(666, "Frank", "frank")
    ok = await grant_admin(666)
    assert ok is True
    user = await get_user(666)
    assert user is not None
    assert user.is_admin is True


async def test_grant_admin_returns_false_for_missing() -> None:
    assert await grant_admin(9999996) is False


async def test_revoke_admin() -> None:
    await register_user(777, "Grace", "grace")
    await grant_admin(777)
    ok = await revoke_admin(777)
    assert ok is True
    user = await get_user(777)
    assert user is not None
    assert user.is_admin is False


async def test_list_active_users_excludes_blocked() -> None:
    await register_user(801, "H1", "h1")
    await register_user(802, "H2", "h2")
    await block_user(802)
    active = await list_active_users()
    ids = [u.telegram_id for u in active]
    assert 801 in ids
    assert 802 not in ids


async def test_list_blocked_users_returns_only_blocked() -> None:
    await register_user(901, "I1", "i1")
    await register_user(902, "I2", "i2")
    await block_user(901)
    blocked = await list_blocked_users()
    ids = [u.telegram_id for u in blocked]
    assert 901 in ids
    assert 902 not in ids
