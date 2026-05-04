# AI API Setup — Free & Cheap Options

The bot uses any **OpenAI-compatible API** for message generation.
You configure this with three `.env` keys:

```env
OPENAI_API_KEY=...
OPENAI_MODEL=...
OPENAI_BASE_URL=...   # empty for OpenAI, or a provider URL
```

Below are options from free to paid.

---

## Option A — Groq (Recommended for free tier)

Groq provides extremely fast inference with a **generous free tier** — no credit card required.

### Steps

1. Go to **https://console.groq.com** and sign up (free).
2. Navigate to **API Keys** → **Create API Key**.
3. Copy the key.
4. Paste into `.env`:
   ```env
   OPENAI_API_KEY=gsk_...your_groq_key...
   OPENAI_MODEL=llama-3.1-8b-instant
   OPENAI_BASE_URL=https://api.groq.com/openai/v1
   ```

### Free tier limits (as of 2025)
| Model | Requests/min | Tokens/day |
|---|---|---|
| `llama-3.1-8b-instant` | 30 | 500,000 |
| `llama-3.3-70b-versatile` | 30 | 100,000 |

For a scheduler sending a few messages per day, the free tier is more than enough.

---

## Option B — OpenRouter (Free models available)

OpenRouter routes to many providers. Several models are permanently free.

### Steps

1. Go to **https://openrouter.ai** and create an account (free).
2. Navigate to **Keys** → **Create Key**.
3. Copy the key.
4. Paste into `.env`:
   ```env
   OPENAI_API_KEY=sk-or-...your_key...
   OPENAI_MODEL=meta-llama/llama-3.1-8b-instruct:free
   OPENAI_BASE_URL=https://openrouter.ai/api/v1
   ```

Free models on OpenRouter have no daily cost but may have rate limits. Search for `:free` on their models page.

---

## Option C — OpenAI (Pay-per-use, very cheap)

If you prefer OpenAI directly, `gpt-4o-mini` is extremely affordable.

### Steps

1. Go to **https://platform.openai.com** and create an account.
2. Navigate to **API keys** → **Create new secret key**.
3. Add a small amount of credit ($5 lasts months for this use case).
4. Copy the key.
5. Paste into `.env`:
   ```env
   OPENAI_API_KEY=sk-...your_key...
   OPENAI_MODEL=gpt-4o-mini
   OPENAI_BASE_URL=
   ```
   Leave `OPENAI_BASE_URL` empty — the SDK uses OpenAI's endpoint by default.

### Approximate cost

| Model | Per message |
|---|---|
| `gpt-4o-mini` | ~$0.0001 (< 1 cent per 100 messages) |
| `gpt-4o` | ~$0.005 |

---

## Option D — Ollama (100% local, no API key needed)

Run a model on your own machine — completely free, no internet required for generation.

### Steps

1. Install Ollama: **https://ollama.com/download** (Windows installer available).
2. Pull a model:
   ```powershell
   ollama pull llama3.2
   ```
3. Ollama runs a local OpenAI-compatible server on port 11434.
4. Paste into `.env`:
   ```env
   OPENAI_API_KEY=ollama
   OPENAI_MODEL=llama3.2
   OPENAI_BASE_URL=http://localhost:11434/v1
   ```
   The API key value doesn't matter for Ollama — put anything.

> **Note:** Ollama requires a decent CPU/GPU. On a typical laptop, generation takes 3–10 seconds per message, which is fine for a scheduler.

---

## Choosing a Model

| Goal | Recommended |
|---|---|
| Free, fast, good quality | Groq `llama-3.1-8b-instant` |
| Free, best quality | OpenRouter `llama-3.3-70b:free` |
| Best quality, small cost | OpenAI `gpt-4o-mini` |
| Fully offline | Ollama `llama3.2` |

---

## Testing Your Key

After filling `.env`, test generation quickly:

```python
# From project root
uv run python -c "
import asyncio
import sys; sys.path.insert(0, 'src')
from message_scheduler.ai_generator import generate_message
msg = asyncio.run(generate_message('@friend', 'good morning motivation'))
print(msg)
"
```

If it prints a message, your AI setup is working correctly.
