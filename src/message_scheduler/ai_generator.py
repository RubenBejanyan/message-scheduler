import logging

from openai import AsyncOpenAI

from .config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if settings.openai_base_url:
            _client = AsyncOpenAI(
                api_key=settings.openai_api_key, base_url=settings.openai_base_url
            )
        else:
            _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


SYSTEM_PROMPT = """You write short, personal Telegram messages that feel genuine and human.
Rules:
- 2 to 4 sentences max.
- Conversational tone, like a real friend texting.
- Vary your openers — don't always start with "Hey".
- No hashtags. Emojis only when they feel natural.
- Do NOT reveal you are an AI. Sound like the sender wrote it themselves.
- Write in the language that feels most natural for the topic (default: English).
"""


async def generate_message(target_username: str, topic: str) -> str:
    """Generate a personalized message for the given target and topic."""
    recipient = target_username.lstrip("@")
    user_prompt = (
        f"Write a Telegram message to send to @{recipient}.\n"
        f"Topic / context: {topic}\n"
        f"Keep it natural and personal."
    )

    try:
        response = await get_client().chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=200,
            temperature=0.9,
        )
        return response.choices[0].message.content or ""
    except Exception:
        logger.exception("AI generation failed for topic=%r target=%r", topic, target_username)
        raise
