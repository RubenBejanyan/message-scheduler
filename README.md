# Message Scheduler

A Telegram bot that generates personalised AI messages and delivers them on a configurable schedule. Each registered user can create multiple schedules targeting any Telegram user or group, with full control over frequency, language, and topic.

## How it works

1. A user creates a schedule via the bot wizard — picking a recipient, frequency, language, and topic.
2. APScheduler fires the job at the configured interval.
3. Telethon fetches the recipient's name and bio from Telegram to personalise the prompt.
4. The AI generates a short, casual, native-language message.
5. The bot delivers it.

All schedules survive restarts — they are persisted in PostgreSQL and reloaded on startup.

## Features

- **Flexible scheduling** — fixed intervals (`30m`, `2h`, `1d`), daily cron (`daily 09:00`), or random daily windows (`window 09:00-10:30`)
- **Jitter** — add a random delay (±15 min to ±2 h) so messages don't always arrive at the exact same second
- **8 languages** — English, Russian, Armenian, Ukrainian, German, French, Spanish, Italian
- **Recipient context** — Telethon fetches name and bio to personalise each message
- **Multi-user** — any number of registered users, each with their own schedules
- **Admin panel** — `/users` shows every user's active schedules with last-sent and next-run times; admin `/list` surfaces all tasks including legacy ones

## Prerequisites

| Requirement | Where to get it |
|---|---|
| Docker + Docker Compose | [docs.docker.com](https://docs.docker.com/get-docker/) |
| Telegram bot token | [@BotFather](https://t.me/BotFather) |
| Telegram API credentials | [my.telegram.org](https://my.telegram.org) |
| OpenAI or Groq API key | [platform.openai.com](https://platform.openai.com) / [console.groq.com](https://console.groq.com) |
| Python 3.12+ + uv | [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/) — only needed for session setup |

## Setup

### 1. Clone

```bash
git clone https://github.com/RubenBejanyan/message-scheduler.git
cd message-scheduler
```

### 2. Create a Telegram bot

1. Open [@BotFather](https://t.me/BotFather) and send `/newbot`.
2. Follow the prompts — copy the **bot token**.
3. Send `/start` to your new bot so it can message you.

Your **admin ID** is your personal Telegram user ID. You can get it from [@userinfobot](https://t.me/userinfobot).

### 3. Get Telegram API credentials

These allow the bot to read recipient profiles via your personal account (Telethon).

1. Go to [my.telegram.org](https://my.telegram.org) and log in.
2. Click **API development tools**.
3. Create an application — copy **App api_id** and **App api_hash**.

### 4. Set up an AI provider

**Option A — OpenAI**

Create a key at [platform.openai.com/api-keys](https://platform.openai.com/api-keys). Leave `OPENAI_BASE_URL` empty.

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=
```

**Option B — Groq (free tier available)**

Create a key at [console.groq.com/keys](https://console.groq.com/keys).

```env
OPENAI_API_KEY=gsk_...
OPENAI_MODEL=llama-3.1-8b-instant
OPENAI_BASE_URL=https://api.groq.com/openai/v1
```

### 5. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Telegram bot
TELEGRAM_BOT_TOKEN=<your bot token>
TELEGRAM_ADMIN_ID=<your telegram user ID>

# Telegram user account (Telethon)
TELEGRAM_API_ID=<api_id from my.telegram.org>
TELEGRAM_API_HASH=<api_hash from my.telegram.org>
TELETHON_SESSION_PATH=./user_session

# AI provider
OPENAI_API_KEY=<your key>
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=

# Database (keep as-is for Docker)
DATABASE_URL=postgresql+asyncpg://user:password@postgres:5432/dev_db

# Minimum allowed schedule interval
MIN_INTERVAL_MINUTES=5
```

### 6. Authenticate Telethon (one-time)

This creates the `user_session.session` file that the bot uses to read recipient profiles. Run it once on the host — it is interactive.

```bash
uv sync
uv run python setup_session.py
```

You will be prompted for your phone number and the confirmation code Telegram sends you. 2FA is supported.

### 7. Start infrastructure

```bash
cd /path/to/infra
docker compose up -d
```

This starts the shared PostgreSQL and Redis services.

### 8. Start the bot

```bash
cd /path/to/message-scheduler
docker compose up -d
```

Check it started cleanly:

```bash
docker logs message_scheduler --tail 30
```

You should see the Telethon connection, APScheduler start, and bot polling lines.

## Deployment

To redeploy after a code change:

```bash
docker build -t ghcr.io/rubenbejanyan/message-scheduler:latest .
docker compose up -d --force-recreate
```

Pushes to `main` automatically run CI (lint + type check) and build a fresh image via GitHub Actions.

## Bot commands

| Command | Who | Description |
|---|---|---|
| `/start` | Everyone | Register and show help |
| `/schedule` | Registered users | Open the schedule creation wizard |
| `/list` | Registered users | View and cancel active schedules (admin sees all) |
| `/cancel` | Registered users | Shortcut hint — use buttons in `/list` |
| `/users` | Admin | List all users with their active schedules |
| `/help` | Everyone | Show help |

## Schedule formats

| Input | Meaning |
|---|---|
| `30m` | Every 30 minutes |
| `2h` | Every 2 hours |
| `1d` | Every day |
| `daily 09:00` | Every day at 09:00 UTC |
| `window 09:00-10:30` | Daily at a random time between 09:00 and 10:30 UTC |

All times are UTC. Jitter (optional randomisation on top of the schedule) can be added for interval and cron types.

## Infrastructure

The bot depends on a PostgreSQL instance. The database schema is created and migrated automatically on startup — no manual migration step is needed.

Redis is available in the shared infra but not currently used by the bot.

## Project structure

```
src/message_scheduler/
├── main.py            # Entry point and startup orchestration
├── config.py          # Environment-based settings (Pydantic)
├── database.py        # SQLAlchemy async engine and auto-migration
├── models.py          # ORM models: RegisteredUser, ScheduledTask
├── scheduler.py       # APScheduler job management
├── users.py           # User registration and access control
├── ai_generator.py    # OpenAI-compatible message generation
├── telegram_client.py # Telethon client for recipient context
└── bot/
    ├── handlers.py    # Aiogram command and callback handlers
    ├── states.py      # FSM states for schedule wizard
    └── keyboards.py   # Inline keyboard builders
```
