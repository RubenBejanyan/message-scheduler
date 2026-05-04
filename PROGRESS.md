# Progress

## Status: Working — needs persistent service wrapper

The bot runs correctly. All Windows networking issues resolved.

## Done
- Fixed `DATABASE_URL`: `localhost` → `127.0.0.1` (IPv6 resolution conflict with native Windows PostgreSQL)
- Fixed event loop: `loop_factory=asyncio.SelectorEventLoop` (replaces deprecated `set_event_loop_policy`)
- Telethon: `connection_retries=-1`, `auto_reconnect=True` (survives Telegram idle RST)
- aiogram polling: retry loop on `ConnectionResetError` / `OSError`
- SQLAlchemy: `pool_pre_ping=True`, `pool_recycle=300`
- DB init: 5-attempt retry with 4s backoff
- Protocol saved: `C:\projects\tg_bot_creation_protocol.md`

## Next Session
Make the bot persistent — it currently dies when the terminal closes.

**Plan (agreed):** Add as a service to `C:\projects\infra\docker-compose.yml` with `restart: always`.
Needs a `Dockerfile` in this directory and a new service entry in the infra compose file.
