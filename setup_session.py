"""
One-time Telethon session setup.

Run this ONCE to authenticate your Telegram user account:
    uv run python setup_session.py

It will prompt for your phone number and the confirmation code Telegram sends you.
After success, a 'user_session.session' file is created — the main app uses it to
send messages as you without needing to log in again.
"""

import asyncio
import sys
from pathlib import Path

# Allow running from the project root without installing the package
sys.path.insert(0, str(Path(__file__).parent / "src"))

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from message_scheduler.config import settings


async def setup() -> None:
    print("=" * 60)
    print("  Telethon Session Setup")
    print("=" * 60)
    print()
    print(f"Session file will be saved to: {settings.telethon_session_path}.session")
    print()

    client = TelegramClient(
        str(settings.telethon_session_path),
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )

    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"Already authenticated as: {me.first_name} (@{me.username})")
        print("Nothing to do. The session file is ready.")
        await client.disconnect()
        return

    phone = input("Enter your phone number (international format, e.g. +15551234567): ").strip()

    await client.send_code_request(phone)
    code = input("Enter the code Telegram sent you: ").strip()

    try:
        await client.sign_in(phone, code)
    except SessionPasswordNeededError:
        # 2FA is enabled
        password = input("Two-factor auth password: ").strip()
        await client.sign_in(password=password)

    me = await client.get_me()
    print()
    print(f"✅ Authenticated as: {me.first_name} (@{me.username})")
    print(f"Session saved to: {settings.telethon_session_path}.session")
    print()
    print("You can now run the bot with:")
    print("  uv run python -m message_scheduler.main")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(setup())
