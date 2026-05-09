from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram bot
    telegram_bot_token: str
    telegram_admin_id: int

    # AI provider
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = ""  # empty = default OpenAI endpoint

    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/dev_db"

    # Redis (FSM storage)
    redis_url: str = "redis://127.0.0.1:6379/0"

    # App
    min_interval_minutes: int = 5
    max_schedules_per_user: int = 10
    max_consecutive_failures: int = 10

    # Admin REST API (set to secure the /api/* endpoints; leave empty to disable auth)
    api_key: str = ""


settings = Settings()  # type: ignore[call-arg]
