"""AI horoscope generation service.

Uses OpenRouter-compatible API (works with OpenAI, Anthropic, Google, open-source models).
Models are configurable per tier via env vars - change without code deployment.
All prompts are built server-side from user profile data.
Content safety is checked on every generated response.
"""

from datetime import date
import logging

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.crypto import decrypt_pii
from app.core.security import sanitize_for_prompt
from app.models.horoscope import Horoscope
from app.models.user import User, FamilyMember
from app.services.zodiac_service import get_zodiac_info
from app.services.interest_catalog import get_prompt_hints_for_interests
from app.services.content_safety import (
    check_content_safety,
    SAFETY_SYSTEM_INSTRUCTIONS,
)

logger = logging.getLogger(__name__)

# OpenRouter/OpenAI-compatible client
# Switching providers = changing AI_BASE_URL + AI_API_KEY in .env
client = AsyncOpenAI(
    api_key=settings.AI_API_KEY,
    base_url=settings.AI_BASE_URL,
)

# --- PROMPT STRUCTURE ---
# The prompt is composed of 3 parts:
#
# 1. SYSTEM_PROMPT - Role, rules, safety constraints (constant)
# 2. USER_CONTEXT  - Profile data: zodiac, name, gender, interests (from DB)
# 3. HISTORY_CONTEXT - Last 5 horoscopes with like/dislike feedback (from DB)
#
# User has ZERO input into any of these. Everything is server-controlled.

SYSTEM_PROMPT = """Ты - опытный астролог с глубоким знанием астрологии. 
Ты создаешь персонализированные, вдохновляющие гороскопы на русском языке.

Правила:
- Пиши на русском языке
- Гороскоп должен быть конкретным и применимым к жизни человека
- Длина: 150-250 слов
- Тон: теплый, мудрый, вдохновляющий, но не наивный
- Включай конкретные советы на день
- Не используй клише и общие фразы
- Учитывай обратную связь пользователя: если предыдущие гороскопы не понравились, измени подход
- Если предыдущие понравились, сохраняй стиль, но не повторяй содержание
""" + SAFETY_SYSTEM_INSTRUCTIONS


def _build_profile_context(
    zodiac_sign: str,
    gender: str,
    name: str,
    birth_time=None,
    birth_place: str = None,
    interests: list[str] = None,
) -> str:
    """Build user profile context for the prompt.

    All text fields are sanitized. Interests use prompt_hint from catalog.
    """
    zodiac_info = get_zodiac_info(zodiac_sign)

    context_parts = [
        f"Знак зодиака: {zodiac_sign}",
        f"Стихия: {zodiac_info['element']}",
        f"Качество: {zodiac_info['quality']}",
        f"Пол: {sanitize_for_prompt(gender, max_length=20)}",
        f"Имя: {sanitize_for_prompt(name, max_length=100)}",
    ]

    if birth_time:
        context_parts.append(f"Время рождения: {birth_time.strftime('%H:%M')}")

    if birth_place:
        context_parts.append(
            f"Место рождения: {sanitize_for_prompt(birth_place, max_length=200)}"
        )

    if interests:
        # Use catalog prompt_hints instead of raw IDs
        hints = get_prompt_hints_for_interests(interests)
        if hints:
            context_parts.append(
                f"Интересующие сферы жизни: {'; '.join(hints)}"
            )

    return "\n".join(context_parts)


def _build_history_context(history: list[Horoscope]) -> str:
    """Build history context from previous horoscopes with feedback."""
    if not history:
        return "История предыдущих гороскопов отсутствует."

    history_parts = ["Предыдущие гороскопы и обратная связь:"]

    for h in history:
        feedback_text = {
            "like": "ПОНРАВИЛОСЬ пользователю",
            "dislike": "НЕ ПОНРАВИЛОСЬ пользователю",
            None: "нет обратной связи",
        }.get(h.feedback, "нет обратной связи")

        history_parts.append(
            f"\n--- Гороскоп от {h.horoscope_date} [{feedback_text}] ---\n"
            f"{h.horoscope_text[:200]}..."
        )

    return "\n".join(history_parts)


def build_full_prompt(
    zodiac_sign: str,
    gender: str,
    name: str,
    target_date: date,
    birth_time=None,
    birth_place: str = None,
    interests: list[str] = None,
    history: list[Horoscope] = None,
) -> tuple[str, str]:
    """Build the complete prompt pair (system + user).

    Exposed as a public function for prompt testing/debugging.
    Returns (system_prompt, user_prompt).
    """
    profile_context = _build_profile_context(
        zodiac_sign=zodiac_sign,
        gender=gender,
        name=name,
        birth_time=birth_time,
        birth_place=birth_place,
        interests=interests,
    )
    history_context = _build_history_context(history or [])

    user_prompt = f"""Составь персональный гороскоп на {target_date.strftime('%d.%m.%Y')} для этого человека:

{profile_context}

{history_context}

Учти обратную связь по предыдущим гороскопам. Если что-то не понравилось - измени стиль и подход.
Если понравилось - сохрани тон, но предложи свежее содержание.
"""

    return SYSTEM_PROMPT, user_prompt


async def generate_horoscope_for_user(
    user: User,
    target_date: date,
    history: list[Horoscope],
    is_premium: bool = False,
) -> tuple[str, str, str, bool]:
    """Generate a personalized horoscope for the user."""
    name = decrypt_pii(user.name_encrypted)
    birth_place = decrypt_pii(user.birth_place_encrypted) if user.birth_place_encrypted else None

    return await _generate(
        zodiac_sign=user.zodiac_sign,
        gender=user.gender,
        name=name,
        birth_time=user.birth_time,
        birth_place=birth_place,
        interests=user.interests or [],
        target_date=target_date,
        history=history,
        is_premium=is_premium,
    )


async def generate_horoscope_for_family_member(
    member: FamilyMember,
    target_date: date,
    history: list[Horoscope],
    is_premium: bool = False,
) -> tuple[str, str, str, bool]:
    """Generate a personalized horoscope for a family member."""
    name = decrypt_pii(member.name_encrypted)

    return await _generate(
        zodiac_sign=member.zodiac_sign,
        gender=member.gender,
        name=name,
        birth_time=member.birth_time,
        birth_place=None,
        interests=member.interests or [],
        target_date=target_date,
        history=history,
        is_premium=is_premium,
    )


async def _generate(
    zodiac_sign: str,
    gender: str,
    name: str,
    birth_time,
    birth_place: str | None,
    interests: list[str],
    target_date: date,
    history: list[Horoscope],
    is_premium: bool,
) -> tuple[str, str, str, bool]:
    """Internal generation logic.

    Returns (horoscope_text, prompt_used, model_used, safety_passed).
    """
    # Select model from config based on subscription tier
    model = settings.AI_MODEL_PREMIUM if is_premium else settings.AI_MODEL_FREE

    system_prompt, user_prompt = build_full_prompt(
        zodiac_sign=zodiac_sign,
        gender=gender,
        name=name,
        target_date=target_date,
        birth_time=birth_time,
        birth_place=birth_place,
        interests=interests,
        history=history,
    )

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=settings.AI_MAX_TOKENS,
            temperature=settings.AI_TEMPERATURE,
        )

        horoscope_text = response.choices[0].message.content.strip()

        # Content safety check
        is_safe, violation = check_content_safety(horoscope_text)
        if not is_safe:
            logger.warning(
                "Generated horoscope FAILED safety check: %s (model=%s). Regenerating.",
                violation, model,
            )
            # Retry once with explicit safety reminder
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": horoscope_text},
                    {
                        "role": "user",
                        "content": (
                            "Этот гороскоп содержит недопустимый контент. "
                            "Перепиши полностью в позитивном и безопасном тоне."
                        ),
                    },
                ],
                max_tokens=settings.AI_MAX_TOKENS,
                temperature=0.7,
            )
            horoscope_text = response.choices[0].message.content.strip()

            is_safe, violation = check_content_safety(horoscope_text)
            if not is_safe:
                horoscope_text = _safe_fallback(name, zodiac_sign)
                return horoscope_text, "SAFETY_FALLBACK", model, False

        return horoscope_text, user_prompt, model, True

    except Exception as e:
        logger.error("AI generation failed (model=%s): %s", model, str(e), exc_info=True)
        fallback_text = _safe_fallback(name, zodiac_sign)
        return fallback_text, "FALLBACK (ai_generation_error)", "fallback", True


def _safe_fallback(name: str, zodiac_sign: str) -> str:
    """Generate a safe, generic horoscope as fallback."""
    safe_name = sanitize_for_prompt(name, max_length=50)
    return (
        f"Дорогой(ая) {safe_name}, сегодня звезды советуют тебе "
        f"быть внимательнее к знакам вселенной. "
        f"Как {zodiac_sign}, ты обладаешь особой интуицией - "
        f"доверься ей сегодня. День благоприятен для новых начинаний "
        f"и важных решений. Не бойся перемен."
    )
