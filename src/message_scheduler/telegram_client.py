import logging

from telethon import TelegramClient
from telethon.errors import FloodWaitError, UserPrivacyRestrictedError

from .config import settings

logger = logging.getLogger(__name__)

_client: TelegramClient | None = None


def get_telegram_client() -> TelegramClient:
    global _client
    if _client is None:
        _client = TelegramClient(
            str(settings.telethon_session_path),
            settings.telegram_api_id,
            settings.telegram_api_hash,
            connection_retries=-1,  # retry forever — Telegram sends RST on idle connections
            retry_delay=3,
            auto_reconnect=True,
        )
    return _client


async def start_client() -> None:
    client = get_telegram_client()
    if not client.is_connected():
        # No interactive prompt — session file must already exist (run setup_session.py first)
        await client.start()
        me = await client.get_me()
        logger.info("Telethon connected as: %s (@%s)", me.first_name, me.username)


async def stop_client() -> None:
    if _client and _client.is_connected():
        await _client.disconnect()


async def send_message_as_user(target_username: str, text: str) -> None:
    """Send a Telegram message FROM the authenticated user account."""
    client = get_telegram_client()
    try:
        await client.send_message(target_username, text)
        logger.info("Sent message to %s", target_username)
    except FloodWaitError as e:
        logger.warning("FloodWait: must wait %d seconds before sending again", e.seconds)
        raise
    except UserPrivacyRestrictedError:
        logger.error("Cannot send to %s — their privacy settings block messages", target_username)
        raise
    except Exception:
        logger.exception("Failed to send message to %s", target_username)
        raise
