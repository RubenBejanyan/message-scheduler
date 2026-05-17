# ChronoPost

**[@Message_AI_Scheduler_bot](https://t.me/Message_AI_Scheduler_bot)** — try it on Telegram

A Telegram bot that schedules and delivers messages automatically — either AI-generated in your language or from your own custom text, photo, voice, document, or video.

## How it works

1. A user creates a schedule via the bot wizard — picking recipients, frequency, message mode, and optional quiet hours.
2. APScheduler fires the job at the configured time.
3. The bot generates or picks a message and delivers it to every target.
4. All schedules survive restarts — persisted in PostgreSQL and restored on startup.

## Features

- **Two message modes**
  - 🤖 AI-generated — short, casual, native-language messages via any OpenAI-compatible API
  - ✍️ Exact — send your own text (rotate randomly from a list), or upload a photo / voice / document / video
- **Media support** — schedule photo, voice note, document, or video alongside text messages
- **Flexible scheduling**
  - Fixed intervals: `30m`, `2h`, `1d`, `1d 6h`, `2h 30m` (compound units supported)
  - Daily cron: `daily 09:00`
  - Random daily window: `window 09:00-10:30`
  - One-shot: `once 2026-05-20 14:30`
- **Multi-target broadcasting** — send to multiple recipients in a single schedule
- **Blackout / quiet hours** — define a daily window (e.g. `23:00-08:00`) when sends are suppressed
- **Repeat count** — optionally limit a schedule to N sends, then auto-deactivate
- **Jitter** — optional random delay (±15 min to ±2 h) so messages don't arrive at the exact same second
- **8 languages** — English, Russian, Armenian, Ukrainian, German, French, Spanish, Italian
- **Pause & resume** — suspend a schedule without cancelling it
- **Clone** — duplicate an existing schedule as a starting point
- **Edit in place** — change topic, language, frequency, recipient, or messages without recreating
- **Message history** — view the last 10 delivered messages per schedule
- **Auto-pause on failure** — after 10 consecutive send failures the schedule pauses automatically and notifies the owner
- **Web admin panel** — manage users and schedules at `/admin` (password-protected)
- **Multi-user** — open registration, admin-controlled blocking
- **Two-tier admin** — master admin (env var) + delegated admins (granted per user)
- **Redis FSM** — wizard state survives container restarts

## Bot commands

| Command | Who | Description |
|---|---|---|
| `/start` | Everyone | Register and show help |
| `/schedule` | Registered users | Open the schedule creation wizard |
| `/list` | Registered users | View and manage active schedules (admin sees all) |
| `/cancel` | Registered users | Cancel a schedule — shows an interactive list with cancel buttons |
| `/id` | Everyone | Get the current chat's numeric ID (useful for scheduling to groups without a @username) |
| `/users` | Master admin | List all users with schedules; block/unblock, grant/revoke admin |
| `/help` | Everyone | Show help |

## Schedule formats

| Input | Meaning |
|---|---|
| `30m` | Every 30 minutes |
| `2h` | Every 2 hours |
| `1d` | Every day |
| `1d 6h` | Every 1 day and 6 hours |
| `2h 30m` | Every 2 hours and 30 minutes |
| `daily 09:00` | Every day at 09:00 in the chosen timezone |
| `window 09:00-10:30` | Daily at a random time between 09:00 and 10:30 |
| `once 2026-05-20 14:30` | Send once on that date and time |

## Prerequisites

| Requirement | Where to get it |
|---|---|
| Docker + Docker Compose | [docs.docker.com](https://docs.docker.com/get-docker/) |
| Telegram bot token | [@BotFather](https://t.me/BotFather) |
| OpenAI or Groq API key | [platform.openai.com](https://platform.openai.com) / [console.groq.com](https://console.groq.com) |

## Deployment

### 1. Server setup

Run once on a fresh Ubuntu 24.04 server:

```bash
curl -fsSL https://raw.githubusercontent.com/RubenBejanyan/message-scheduler/main/deploy/server-setup.sh | bash
```

### 2. Start shared infrastructure (Postgres + Redis)

```bash
mkdir -p /opt/infra && cd /opt/infra
curl -fsSL https://raw.githubusercontent.com/RubenBejanyan/message-scheduler/main/deploy/infra-compose.yml -o docker-compose.yml
cat > .env <<EOF
POSTGRES_PASSWORD=your_strong_password
EOF
docker compose up -d
```

### 3. Deploy the bot

```bash
mkdir -p /opt/message_scheduler && cd /opt/message_scheduler
curl -fsSL https://raw.githubusercontent.com/RubenBejanyan/message-scheduler/main/docker-compose.yml -o docker-compose.yml
nano .env   # fill in values from deploy/.env.example
docker compose pull
docker compose up -d
```

### 4. Verify

```bash
docker logs message_scheduler -f
```

The database schema is created and migrated automatically on first startup — no manual migration step needed.

### Updates

Pushing to `main` triggers GitHub Actions to build and publish a new Docker image. **Watchtower** on the server detects the new image within 60 seconds and redeploys automatically — no manual intervention needed.

## Configuration

See [`deploy/.env.example`](deploy/.env.example) for all available options.

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `TELEGRAM_ADMIN_ID` | Your Telegram user ID (master admin) |
| `OPENAI_API_KEY` | API key for OpenAI or Groq |
| `OPENAI_MODEL` | Model name (e.g. `gpt-4o-mini`, `llama-3.1-8b-instant`) |
| `OPENAI_BASE_URL` | Leave empty for OpenAI; set to `https://api.groq.com/openai/v1` for Groq |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `API_KEY` | Password for the `/admin` web panel (leave empty to disable auth) |
| `MIN_INTERVAL_MINUTES` | Minimum allowed schedule interval (default: 5) |
| `MAX_SCHEDULES_PER_USER` | Schedule cap per user, admins exempt (default: 10) |
| `MAX_CONSECUTIVE_FAILURES` | Auto-pause threshold (default: 10) |

## Web admin panel

The bot exposes a web UI at `http://<your-server>:8080/admin` for managing users and schedules without Telegram commands. Log in with the `API_KEY` value from your `.env` (leave it empty to skip authentication during development).

## Project structure

```
src/message_scheduler/
├── main.py          # Entry point — migrations, APScheduler, bot polling, API server
├── config.py        # Environment-based settings (Pydantic)
├── database.py      # SQLAlchemy async engine and session factory
├── models.py        # ORM models: RegisteredUser, ScheduledTask, SentMessage
├── scheduler.py     # APScheduler job management and task CRUD
├── users.py         # User registration and access control
├── ai_generator.py  # OpenAI-compatible message generation
├── admin.py         # sqladmin web panel views
└── bot/
    ├── handlers.py  # Aiogram command and callback handlers
    ├── states.py    # FSM states for schedule and edit wizards
    └── keyboards.py # Inline keyboard builders

alembic/             # Database migrations (run automatically on startup)
deploy/              # Server setup scripts and env template
```

## Infrastructure

The bot runs as a single Docker container and connects to shared Postgres and Redis services via Docker network `infra_net`.

| Service | Purpose |
|---|---|
| PostgreSQL | Persists users, schedules, and message history |
| Redis | Stores FSM wizard state across restarts |
| Watchtower | Auto-deploys new images on push to main |
