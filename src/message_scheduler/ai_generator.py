import logging

from openai import AsyncOpenAI

from .config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None

# Characters that LLMs sometimes wrap the entire message in
_QUOTE_CHARS = '"\'«»„""‟❝❞'

_SYSTEM_PROMPT = """\
You are composing a short, personal Telegram message on behalf of a real person.

LANGUAGE: Write as a NATIVE speaker of {language}. Think and compose directly \
in {language} — do NOT mentally translate from English. Use idioms, register, \
and expressions that feel completely natural in {language} culture.

{recipient_block}\
RULES:
- 2–4 sentences maximum
- Casual, warm, friend-to-friend tone
- Vary your opener every time — avoid starting with "Hey" or its local equivalents
- No hashtags. Emojis only if they genuinely fit the context
- Do NOT reveal you are an AI
- Do NOT wrap the message in quotation marks
"""


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


def _build_system_prompt(language: str, recipient_info: dict[str, str]) -> str:
    parts: list[str] = []
    if name := recipient_info.get("name"):
        parts.append(f"Recipient's name: {name}")
    if bio := recipient_info.get("bio"):
        parts.append(f"Recipient's bio: {bio[:300]}")
    if recipient_info.get("type") == "group":
        parts.append("This is a group chat — write a message appropriate for a group audience")

    recipient_block = ""
    if parts:
        recipient_block = "RECIPIENT CONTEXT:\n" + "\n".join(f"- {p}" for p in parts) + "\n\n"

    return _SYSTEM_PROMPT.format(language=language, recipient_block=recipient_block)


async def generate_message(
    target_username: str,
    topic: str,
    language: str = "English",
    recipient_info: dict[str, str] | None = None,
) -> str:
    """Generate a personalised message for the given target, topic, and language."""
    recipient = target_username.lstrip("@")
    system = _build_system_prompt(language, recipient_info or {})

    name_hint = ""
    if recipient_info and (name := recipient_info.get("name")):
        name_hint = f"Their name is {name}. "

    user_prompt = (
        f"Write a Telegram message to @{recipient}. {name_hint}"
        f"Topic / context: {topic}\n"
        f"Compose directly in {language} — do not translate."
    )

    try:
        response = await get_client().chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=200,
            temperature=0.9,
        )
        raw = (response.choices[0].message.content or "").strip()
        return raw.strip(_QUOTE_CHARS)
    except Exception:
        logger.exception("AI generation failed for topic=%r target=%r", topic, target_username)
        raise
