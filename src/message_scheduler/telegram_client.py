import logging
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
    UserPrivacyRestrictedError,
)
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import User

from .config import settings

logger = logging.getLogger(__name__)

# Owner's client — used for get_recipient_info() and "send as owner" tasks
_owner_client: TelegramClient | None = None

# Per-user clients for "send as user" scheduled tasks
_user_clients: dict[int, TelegramClient] = {}


def _sessions_dir() -> Path:
    return Path(settings.telethon_session_path).parent / "sessions"


def _user_session_path(user_id: int) -> str:
    return str(_sessions_dir() / str(user_id))


def get_telegram_client() -> TelegramClient:
    global _owner_client
    if _owner_client is None:
        _owner_client = TelegramClient(
            str(settings.telethon_session_path),
            settings.telegram_api_id,
            settings.telegram_api_hash,
            connection_retries=-1,
            retry_delay=3,
            auto_reconnect=True,
        )
    return _owner_client


def _get_user_client(user_id: int) -> TelegramClient:
    if user_id not in _user_clients:
        _user_clients[user_id] = TelegramClient(
            _user_session_path(user_id),
            settings.telegram_api_id,
            settings.telegram_api_hash,
            connection_retries=-1,
            retry_delay=3,
            auto_reconnect=True,
        )
    return _user_clients[user_id]


# ── Owner client lifecycle ────────────────────────────────────────────────────


async def start_client() -> None:
    client = get_telegram_client()
    if not client.is_connected():
        await client.start()
        me = await client.get_me()
        logger.info("Telethon connected as: %s (@%s)", me.first_name, me.username)


async def stop_client() -> None:
    if _owner_client and _owner_client.is_connected():
        await _owner_client.disconnect()


# ── Per-user client lifecycle ─────────────────────────────────────────────────


async def reconnect_user_clients() -> list[int]:
    """On startup, reconnect saved per-user sessions. Returns IDs of expired sessions."""
    sessions = _sessions_dir()
    if not sessions.exists():
        return []

    expired: list[int] = []
    for f in sessions.glob("*.session"):
        try:
            user_id = int(f.stem)
        except ValueError:
            continue
        client = _get_user_client(user_id)
        try:
            await client.connect()
            if await client.is_user_authorized():
                logger.info("Reconnected user session: %d", user_id)
            else:
                logger.warning("User session %d expired — removing", user_id)
                await _purge_user_session(user_id)
                expired.append(user_id)
        except Exception:
            logger.exception("Failed to reconnect user session %d", user_id)
            expired.append(user_id)

    return expired


async def stop_all_user_clients() -> None:
    for client in _user_clients.values():
        if client.is_connected():
            await client.disconnect()
    _user_clients.clear()


async def _purge_user_session(user_id: int) -> None:
    """Disconnect and delete the session file for a user."""
    client = _user_clients.pop(user_id, None)
    if client and client.is_connected():
        await client.disconnect()
    session_file = Path(_user_session_path(user_id) + ".session")
    if session_file.exists():
        session_file.unlink()


# ── Per-user auth flow ────────────────────────────────────────────────────────


async def start_user_auth(user_id: int, phone: str) -> str:
    """Send OTP to the phone number. Returns phone_code_hash for the next step."""
    _sessions_dir().mkdir(parents=True, exist_ok=True)
    client = _get_user_client(user_id)
    if not client.is_connected():
        await client.connect()
    result = await client.send_code_request(phone)
    return str(result.phone_code_hash)


async def complete_user_code(
    user_id: int, phone: str, code: str, phone_hash: str
) -> str:
    """
    Verify OTP. Returns one of:
      "ok"      — authenticated
      "2fa"     — correct code but 2FA password required
      "expired" — code expired, must restart
      "invalid" — wrong code
    """
    client = _get_user_client(user_id)
    try:
        await client.sign_in(phone, code, phone_code_hash=phone_hash)
        return "ok"
    except SessionPasswordNeededError:
        return "2fa"
    except PhoneCodeExpiredError:
        return "expired"
    except PhoneCodeInvalidError:
        return "invalid"


async def complete_user_2fa(user_id: int, password: str) -> bool:
    """Verify 2FA password. Returns True on success."""
    client = _get_user_client(user_id)
    try:
        await client.sign_in(password=password)
        return True
    except Exception:
        logger.exception("2FA sign-in failed for user %d", user_id)
        return False


async def disconnect_user(user_id: int) -> None:
    """Remove a user's session entirely."""
    await _purge_user_session(user_id)


async def is_user_connected(user_id: int) -> bool:
    client = _user_clients.get(user_id)
    if client is None:
        return False
    return bool(client.is_connected() and await client.is_user_authorized())


# ── Messaging ─────────────────────────────────────────────────────────────────


async def get_recipient_info(target: str) -> dict[str, str]:
    """Fetch name/bio/type for a target using the owner's Telethon session."""
    client = get_telegram_client()
    try:
        entity = await client.get_entity(target)
        if isinstance(entity, User):
            name = " ".join(p for p in [entity.first_name or "", entity.last_name or ""] if p)
            bio = ""
            try:
                full = await client(GetFullUserRequest(entity))
                bio = (getattr(full.full_user, "about", None) or "").strip()
            except Exception:
                pass
            return {"name": name, "type": "user", "bio": bio}
        else:
            title = getattr(entity, "title", None) or target
            return {"name": title, "type": "group", "bio": ""}
    except Exception:
        logger.warning("Could not fetch recipient info for %s", target)
        return {}


async def send_message_as_owner(target_username: str, text: str) -> None:
    """Send via the owner's Telethon session."""
    client = get_telegram_client()
    try:
        await client.send_message(target_username, text)
        logger.info("Sent message to %s (as owner)", target_username)
    except FloodWaitError as e:
        logger.warning("FloodWait: %ds", e.seconds)
        raise
    except UserPrivacyRestrictedError:
        logger.error("Cannot send to %s — privacy settings", target_username)
        raise
    except Exception:
        logger.exception("Failed to send to %s", target_username)
        raise


async def send_message_as_user_session(user_id: int, target: str, text: str) -> None:
    """Send via a registered user's personal Telethon session."""
    client = _user_clients.get(user_id)
    if client is None or not client.is_connected():
        raise RuntimeError(f"No active session for user {user_id} — they must /connect again")
    try:
        await client.send_message(target, text)
        logger.info("Sent message to %s (as user %d)", target, user_id)
    except FloodWaitError as e:
        logger.warning("FloodWait for user %d: %ds", user_id, e.seconds)
        raise
    except UserPrivacyRestrictedError:
        logger.error("Cannot send to %s — privacy settings", target)
        raise
    except Exception:
        logger.exception("Failed to send as user %d to %s", user_id, target)
        raise
