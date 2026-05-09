"""API integration tests — real SQLite for user/stats routes, mocks for scheduler routes."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

import message_scheduler.api.schedules as sched_api_mod
import message_scheduler.users as users_mod
from message_scheduler.api import create_app
from message_scheduler.models import ScheduledTask

# ── helpers ───────────────────────────────────────────────────────────────────

def _make_task(**kwargs: object) -> ScheduledTask:
    defaults: dict[str, object] = dict(
        id=1,
        user_telegram_id=100,
        target_username="@target",
        topic="Test topic",
        interval_type="interval",
        interval_value="3600",
        interval_label="every 1 hour(s)",
        jitter_seconds=None,
        language="English",
        timezone="UTC",
        is_active=True,
        is_paused=False,
        message_mode="ai",
        messages_json=None,
        consecutive_failures=0,
        last_error=None,
        created_at=datetime.now(tz=UTC),
        last_sent_at=None,
        job_id="job-abc-1",
    )
    defaults.update(kwargs)
    task = ScheduledTask.__new__(ScheduledTask)
    task.__dict__.update(defaults)
    return task


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── /health ───────────────────────────────────────────────────────────────────

async def test_health_returns_ok(client: AsyncClient) -> None:
    async with client as c:
        resp = await c.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ── /api/stats ────────────────────────────────────────────────────────────────

async def test_stats_returns_zeros(patch_full_db: None, client: AsyncClient) -> None:
    async with client as c:
        resp = await c.get("/api/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_users"] == 0
    assert data["active_schedules"] == 0
    assert data["messages_sent_total"] == 0


async def test_stats_counts_registered_users(patch_full_db: None, client: AsyncClient) -> None:
    await users_mod.register_user(10, "Alice", "alice")
    await users_mod.register_user(11, "Bob", "bob")
    await users_mod.block_user(11)
    async with client as c:
        resp = await c.get("/api/stats")
    data = resp.json()
    assert data["total_users"] == 2
    assert data["approved_users"] == 1


# ── /api/users ────────────────────────────────────────────────────────────────

async def test_list_users_empty(patch_full_db: None, client: AsyncClient) -> None:
    async with client as c:
        resp = await c.get("/api/users")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_users_after_register(patch_full_db: None, client: AsyncClient) -> None:
    await users_mod.register_user(20, "Carol", "carol")
    async with client as c:
        resp = await c.get("/api/users")
    assert resp.status_code == 200
    users = resp.json()
    assert len(users) == 1
    assert users[0]["telegram_id"] == 20
    assert users[0]["first_name"] == "Carol"
    assert users[0]["is_approved"] is True
    assert users[0]["is_admin"] is False


async def test_get_user_found(patch_full_db: None, client: AsyncClient) -> None:
    await users_mod.register_user(30, "Dave", "dave")
    async with client as c:
        resp = await c.get("/api/users/30")
    assert resp.status_code == 200
    assert resp.json()["telegram_id"] == 30


async def test_get_user_not_found(patch_full_db: None, client: AsyncClient) -> None:
    async with client as c:
        resp = await c.get("/api/users/9999999")
    assert resp.status_code == 404


async def test_block_user_via_api(patch_full_db: None, client: AsyncClient) -> None:
    await users_mod.register_user(40, "Eve", "eve")
    async with client as c:
        resp = await c.post("/api/users/40/block")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        detail = await c.get("/api/users/40")
    assert detail.json()["is_approved"] is False


async def test_block_user_not_found_returns_404(patch_full_db: None, client: AsyncClient) -> None:
    async with client as c:
        resp = await c.post("/api/users/9999998/block")
    assert resp.status_code == 404


async def test_unblock_user_via_api(patch_full_db: None, client: AsyncClient) -> None:
    await users_mod.register_user(50, "Frank", "frank")
    await users_mod.block_user(50)
    async with client as c:
        resp = await c.post("/api/users/50/unblock")
    assert resp.status_code == 200
    user = await users_mod.get_user(50)
    assert user is not None
    assert user.is_approved is True


async def test_grant_admin_via_api(patch_full_db: None, client: AsyncClient) -> None:
    await users_mod.register_user(60, "Grace", "grace")
    async with client as c:
        resp = await c.post("/api/users/60/grant-admin")
    assert resp.status_code == 200
    user = await users_mod.get_user(60)
    assert user is not None
    assert user.is_admin is True


async def test_revoke_admin_via_api(patch_full_db: None, client: AsyncClient) -> None:
    await users_mod.register_user(70, "Hank", "hank")
    await users_mod.grant_admin(70)
    async with client as c:
        resp = await c.post("/api/users/70/revoke-admin")
    assert resp.status_code == 200
    user = await users_mod.get_user(70)
    assert user is not None
    assert user.is_admin is False


# ── /api/schedules (mocked scheduler) ────────────────────────────────────────

async def test_list_schedules_empty(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sched_api_mod, "list_all_active_tasks", AsyncMock(return_value=[]))
    async with client as c:
        resp = await c.get("/api/schedules")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_schedules_returns_tasks(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = _make_task()
    monkeypatch.setattr(sched_api_mod, "list_all_active_tasks", AsyncMock(return_value=[task]))
    monkeypatch.setattr(sched_api_mod, "get_next_run_time", MagicMock(return_value=None))
    async with client as c:
        resp = await c.get("/api/schedules")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == 1
    assert data[0]["target_username"] == "@target"


async def test_get_schedule_not_found(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sched_api_mod, "get_task", AsyncMock(return_value=None))
    async with client as c:
        resp = await c.get("/api/schedules/999")
    assert resp.status_code == 404


async def test_get_schedule_found(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = _make_task(id=5)
    monkeypatch.setattr(sched_api_mod, "get_task", AsyncMock(return_value=task))
    monkeypatch.setattr(sched_api_mod, "get_next_run_time", MagicMock(return_value=None))
    async with client as c:
        resp = await c.get("/api/schedules/5")
    assert resp.status_code == 200
    assert resp.json()["id"] == 5


async def test_cancel_schedule_not_found(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sched_api_mod, "cancel_task", AsyncMock(return_value=False))
    async with client as c:
        resp = await c.delete("/api/schedules/999")
    assert resp.status_code == 404


async def test_cancel_schedule_ok(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sched_api_mod, "cancel_task", AsyncMock(return_value=True))
    async with client as c:
        resp = await c.delete("/api/schedules/1")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


async def test_pause_schedule_ok(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sched_api_mod, "pause_task", AsyncMock(return_value=True))
    async with client as c:
        resp = await c.post("/api/schedules/1/pause")
    assert resp.status_code == 200


async def test_resume_schedule_ok(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sched_api_mod, "resume_task", AsyncMock(return_value=True))
    async with client as c:
        resp = await c.post("/api/schedules/1/resume")
    assert resp.status_code == 200


async def test_fire_schedule_ok(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sched_api_mod, "fire_task_now", AsyncMock(return_value="Hello!"))
    async with client as c:
        resp = await c.post("/api/schedules/1/fire")
    assert resp.status_code == 200
    assert resp.json()["text"] == "Hello!"


async def test_fire_schedule_not_found(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sched_api_mod, "fire_task_now", AsyncMock(side_effect=ValueError("not found"))
    )
    async with client as c:
        resp = await c.post("/api/schedules/999/fire")
    assert resp.status_code == 404


async def test_schedule_history_ok(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sched_api_mod, "get_task_history", AsyncMock(return_value=[]))
    async with client as c:
        resp = await c.get("/api/schedules/1/history")
    assert resp.status_code == 200
    assert resp.json() == []


# ── auth enforcement ──────────────────────────────────────────────────────────

async def test_auth_rejects_wrong_key(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    import message_scheduler.api.deps as deps_mod

    monkeypatch.setattr(deps_mod.settings, "api_key", "secret-key")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"  # type: ignore[arg-type]
    ) as c:
        resp = await c.get("/api/users")
    assert resp.status_code == 403


async def test_auth_accepts_correct_key(
    patch_full_db: None, app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    import message_scheduler.api.deps as deps_mod

    monkeypatch.setattr(deps_mod.settings, "api_key", "secret-key")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"  # type: ignore[arg-type]
    ) as c:
        resp = await c.get("/api/users", headers={"X-API-Key": "secret-key"})
    assert resp.status_code == 200
