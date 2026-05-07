import logging
from pathlib import Path

from telethon import TelegramClient
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import User

from .config import settings

logger = logging.getLogger(__name__)

_client: TelegramClient | None = None
_available: bool = False  # True only after a successful start_client()


def get_telegram_client() -> TelegramClient:
    global _client
    if _client is None:
        _client = TelegramClient(
            str(settings.telethon_session_path),
            settings.telegram_api_id,
            settings.telegram_api_hash,
            connection_retries=-1,
            retry_delay=3,
            auto_reconnect=True,
        )
    return _client


async def start_client() -> None:
    """Connect Telethon. Skips silently if no session file exists."""
    global _available
    session_file = Path(str(settings.telethon_session_path) + ".session")
    if not session_file.exists():
        logger.warning(
            "Telethon session file not found (%s). "
            "Recipient info enrichment disabled. "
            "Run 'uv run python setup_session.py' to enable it.",
            session_file,
        )
        return

    client = get_telegram_client()
    if not client.is_connected():
        await client.start()
        me = await client.get_me()
        logger.info("Telethon connected as: %s (@%s)", me.first_name, me.username)
    _available = True


async def stop_client() -> None:
    if _client and _client.is_connected():
        await _client.disconnect()


async def get_recipient_info(target: str) -> dict[str, str]:
    """Fetch name/bio/type for a target. Returns empty dict if Telethon is unavailable."""
    if not _available:
        return {}
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
