"""AI horoscope generation service.

All user data is decrypted server-side before building prompts.
Users have NO access to prompt input - everything is constructed from their profile.
Content safety is checked on every generated response.
"""

from datetime import date
import logging

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.crypto import decrypt_pii
from app.core.security import sanitize_for_prompt
from app.models.horoscope import Horoscope
from app.models.user import User, FamilyMember, InterestCategory
from app.services.zodiac_service import get_zodiac_info
from app.services.content_safety import (
    check_content_safety,
    SAFETY_SYSTEM_INSTRUCTIONS,
)

logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

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

# Mapping of interest enum values to Russian display names
INTEREST_DISPLAY_NAMES = {
    InterestCategory.LOVE: "любовь и отношения",
    InterestCategory.CAREER: "карьера и работа",
    InterestCategory.HEALTH: "здоровье",
    InterestCategory.FINANCE: "финансы",
    InterestCategory.FAMILY: "семья",
    InterestCategory.EDUCATION: "образование и развитие",
    InterestCategory.TRAVEL: "путешествия",
    InterestCategory.CREATIVITY: "творчество",
}


def _build_profile_context(
    zodiac_sign: str,
    gender: str,
    name: str,
    birth_time=None,
    birth_place: str = None,
    interests: list[str] = None,
) -> str:
    """Build profile context string for the prompt.

    Accepts already-decrypted values. All text is sanitized.
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
        # Only use predefined interest names - no user-supplied text
        valid_interests = []
        for interest in interests:
            try:
                cat = InterestCategory(interest)
                display = INTEREST_DISPLAY_NAMES.get(cat, interest)
                valid_interests.append(display)
            except ValueError:
                continue  # Skip unknown interests
        if valid_interests:
            context_parts.append(f"Интересующие сферы: {', '.join(valid_interests)}")

    return "\n".join(context_parts)


def _build_history_context(history: list[Horoscope]) -> str:
    """Build history context from previous horoscopes with feedback."""
    if not history:
        return "История предыдущих гороскопов отсутствует."

    history_parts = ["Предыдущие гороскопы и обратная связь:"]

    for h in history:
        feedback_text = {
            "like": "ПОНРАВИЛОСЬ",
            "dislike": "НЕ ПОНРАВИЛОСЬ",
            None: "нет обратной связи",
        }.get(h.feedback, "нет обратной связи")

        history_parts.append(
            f"\n--- Гороскоп от {h.horoscope_date} [{feedback_text}] ---\n"
            f"{h.horoscope_text[:200]}..."
        )

    return "\n".join(history_parts)


async def generate_horoscope_for_user(
    user: User,
    target_date: date,
    history: list[Horoscope],
    is_premium: bool = False,
) -> tuple[str, str, str, bool]:
    """Generate a personalized horoscope for the user.

    Decrypts PII server-side, builds prompt, generates, checks safety.
    User has NO input into the prompt.

    Returns:
        Tuple of (horoscope_text, prompt_used, model_used, safety_passed)
    """
    # Decrypt PII for prompt building
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
    """Internal generation logic. Returns (text, prompt, model, safety_passed)."""
    model = "gpt-4o" if is_premium else "gpt-4o-mini"

    profile_context = _build_profile_context(
        zodiac_sign=zodiac_sign,
        gender=gender,
        name=name,
        birth_time=birth_time,
        birth_place=birth_place,
        interests=interests,
    )
    history_context = _build_history_context(history)

    user_prompt = f"""Составь персональный гороскоп на {target_date.strftime('%d.%m.%Y')} для этого человека:

{profile_context}

{history_context}

Учти обратную связь по предыдущим гороскопам. Если что-то не понравилось - измени стиль и подход.
Если понравилось - сохрани тон, но предложи свежее содержание.
"""

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=500,
            temperature=0.8,
        )

        horoscope_text = response.choices[0].message.content.strip()

        # Content safety check
        is_safe, violation = check_content_safety(horoscope_text)
        if not is_safe:
            logger.warning(
                "Generated horoscope FAILED safety check: %s. Regenerating.",
                violation,
            )
            # Retry once with explicit safety reminder
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
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
                max_tokens=500,
                temperature=0.7,
            )
            horoscope_text = response.choices[0].message.content.strip()

            # Check again
            is_safe, violation = check_content_safety(horoscope_text)
            if not is_safe:
                # Use safe fallback
                horoscope_text = _safe_fallback(name, zodiac_sign)
                return horoscope_text, "SAFETY_FALLBACK", model, False

        return horoscope_text, user_prompt, model, True

    except Exception as e:
        logger.error("AI generation failed: %s", str(e), exc_info=True)
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
