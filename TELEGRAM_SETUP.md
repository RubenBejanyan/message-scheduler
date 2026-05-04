# Telegram Setup Guide

This bot uses **two separate Telegram identities**:

| Identity | Purpose | Credential |
|---|---|---|
| **Bot account** (via @BotFather) | Receives your commands | `TELEGRAM_BOT_TOKEN` |
| **Your user account** (via Telethon) | Sends AI messages as you | `TELEGRAM_API_ID` + `TELEGRAM_API_HASH` |

Follow the steps below in order.

---

## Step 1 — Create a Bot with @BotFather

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot`.
3. Choose a display name (e.g. `My Scheduler`).
4. Choose a username ending in `bot` (e.g. `my_scheduler_bot`).
5. BotFather replies with a token like `7123456789:AAF...`. Copy it.
6. Paste it into your `.env` file:
   ```
   TELEGRAM_BOT_TOKEN=7123456789:AAF...
   ```

---

## Step 2 — Find Your Telegram User ID

1. Open Telegram and search for **@userinfobot**.
2. Send `/start`. It replies with your numeric user ID (e.g. `123456789`).
3. Paste it into `.env`:
   ```
   TELEGRAM_OWNER_ID=123456789
   ```
   This ensures the bot only responds to **you**, not random people.

---

## Step 3 — Get Telegram API Credentials (for sending as your account)

These allow Telethon to act on behalf of your Telegram account.

1. Go to **https://my.telegram.org** and log in with your phone number.
2. Click **"API development tools"**.
3. Fill in the form:
   - **App title**: anything (e.g. `Message Scheduler`)
   - **Short name**: anything (e.g. `msgscheduler`)
   - Platform: `Desktop`
4. Click **Create application**.
5. You will see `App api_id` and `App api_hash`. Copy both.
6. Paste them into `.env`:
   ```
   TELEGRAM_API_ID=12345678
   TELEGRAM_API_HASH=0123456789abcdef0123456789abcdef
   ```

> **Security note:** These credentials give full access to your Telegram account.
> Never share them or commit them to git. The `.gitignore` already excludes `.env`.

---

## Step 4 — Authenticate Your User Account (one-time only)

This creates a local session file so the bot can send messages as you.

```bash
# From the project root:
uv run python setup_session.py
```

You will be prompted for:
1. Your phone number (international format, e.g. `+15551234567`)
2. The confirmation code Telegram sends you via SMS or another device
3. Your 2FA password (if you have one enabled)

After success, a file called `user_session.session` appears in the project root.
**Do not delete this file** — it is your persistent login. The `.gitignore` already excludes it.

---

## Step 5 — Configure the Database

Make sure the shared Postgres container is running:

```bash
# From C:\projects\infra\
docker compose up -d
```

The default `.env` already points to it:
```
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/dev_db
```

---

## Step 6 — Start the Bot

```bash
# From C:\projects\apps\message_scheduler\
uv run python -m message_scheduler.main
```

On first run the bot automatically creates the `scheduled_tasks` table in Postgres.

---

## Using the Bot

Open a chat with your bot in Telegram and send:

| Command | Description |
|---|---|
| `/start` | Show welcome message |
| `/schedule` | Create a new scheduled message (3-step wizard) |
| `/list` | View all active schedules |
| `/cancel` | Cancel a schedule (also via button in /list) |

### Example session

```
You: /schedule
Bot: Step 1/3 — Who should receive the messages?

You: @alice
Bot: Step 2/3 — How often should I send?

You: daily 09:00
Bot: Step 3/3 — What should the message be about?

You: good morning, something warm and motivating
Bot: 📋 Confirm your schedule:
      • Recipient: @alice
      • Frequency: daily at 09:00 UTC
      • Topic: good morning, something warm and motivating
     [✅ Confirm] [❌ Cancel]

You: ✅ Confirm
Bot: ✅ Schedule created! (ID: 1)
     I'll send messages to @alice daily at 09:00 UTC.
```

Every day at 09:00 UTC the bot generates a fresh AI message and sends it **from your account** to @alice.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Session file not found` | Run `setup_session.py` first |
| `Unauthorized` on bot token | Check `TELEGRAM_BOT_TOKEN` in `.env` |
| `UserPrivacyRestrictedError` | Target user has privacy settings that block messages from non-contacts. Ask them to add you first. |
| `FloodWaitError` | Telegram rate-limited you. Lower the frequency of your schedule. |
| Bot doesn't respond | Confirm your `TELEGRAM_OWNER_ID` matches your real user ID (use @userinfobot) |
