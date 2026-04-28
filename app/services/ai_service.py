from datetime import date
from typing import Optional

from openai import AsyncOpenAI

from app.core.config import settings
from app.models.horoscope import Horoscope
from app.models.user import User
from app.services.zodiac_service import get_zodiac_info

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
"""


def _build_user_context(user: User) -> str:
    """Build user context string for the prompt."""
    zodiac_info = get_zodiac_info(user.zodiac_sign)

    context_parts = [
        f"Знак зодиака: {user.zodiac_sign}",
        f"Стихия: {zodiac_info['element']}",
        f"Качество: {zodiac_info['quality']}",
        f"Пол: {user.gender}",
        f"Имя: {user.name}",
    ]

    if user.birth_time:
        context_parts.append(f"Время рождения: {user.birth_time.strftime('%H:%M')}")

    if user.birth_place:
        context_parts.append(f"Место рождения: {user.birth_place}")

    if user.interests:
        active_interests = [k for k, v in user.interests.items() if v]
        if active_interests:
            context_parts.append(f"Интересующие сферы: {', '.join(active_interests)}")

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


async def generate_horoscope(
    user: User,
    target_date: date,
    history: list[Horoscope],
    is_premium: bool = False,
) -> tuple[str, str, str]:
    """Generate a personalized horoscope using AI.

    Returns:
        Tuple of (horoscope_text, prompt_used, model_used)
    """
    # Select model based on subscription
    model = "gpt-4o" if is_premium else "gpt-4o-mini"

    # Build the prompt
    user_context = _build_user_context(user)
    history_context = _build_history_context(history)

    user_prompt = f"""Составь персональный гороскоп на {target_date.strftime('%d.%m.%Y')} для этого человека:

{user_context}

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
        return horoscope_text, user_prompt, model

    except Exception as e:
        # Fallback: return a generic message if AI fails
        fallback_text = (
            f"Дорогой(ая) {user.name}, сегодня звезды советуют тебе "
            f"быть внимательнее к знакам вселенной. "
            f"Как {user.zodiac_sign}, ты обладаешь особой интуицией - "
            f"доверься ей сегодня. День благоприятен для новых начинаний "
            f"и важных решений. Не бойся перемен."
        )
        return fallback_text, f"FALLBACK (error: {str(e)})", "fallback"
