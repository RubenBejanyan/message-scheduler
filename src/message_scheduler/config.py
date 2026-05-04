from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram bot
    telegram_bot_token: str
    telegram_owner_id: int

    # Telethon (user account)
    telegram_api_id: int
    telegram_api_hash: str
    telethon_session_path: Path = Path("./user_session")

    # AI provider
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = ""  # empty = default OpenAI endpoint

    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/dev_db"

    # App
    min_interval_minutes: int = 5


settings = Settings()  # type: ignore[call-arg]
