"""Content safety filter for AI-generated horoscopes.

Checks generated text for harmful content before delivering to users.
Blocks content that contains references to:
- Suicide, self-harm, death encouragement
- Criminal activity, violence
- Discrimination, humiliation
- Drug abuse encouragement
- Financial scams or dangerous advice
"""

import re
import logging

logger = logging.getLogger(__name__)

# Patterns that MUST NOT appear in horoscope text
# Each tuple: (pattern, category, description)
BLOCKED_PATTERNS = [
    # Suicide / self-harm / death
    (r"(?i)(покончи|суицид|самоубийств|убей\s+себя|прыгн[иь]\s+с|повес[иь]сь|перереж)", "self_harm", "Self-harm references"),
    (r"(?i)(лучше\s+умереть|не\s+стоит\s+жить|конец\s+жизни|уйти\s+из\s+жизни)", "self_harm", "Death encouragement"),

    # Violence / crime
    (r"(?i)(убей|убить|напади|ограб|укради|украд|поджог|взорв|отрав)", "violence", "Violence/crime"),
    (r"(?i)(нанеси?\s+удар|причини?\s+(вред|боль)|отомсти)", "violence", "Harm encouragement"),

    # Discrimination / humiliation
    (r"(?i)(ты\s+ничтожеств|ты\s+жалк|ты\s+бесполезн|никчемн)", "humiliation", "Humiliation"),
    (r"(?i)(расов|нацист|фашист|геноцид)", "discrimination", "Discrimination"),

    # Drug abuse
    (r"(?i)(употреби?\s+наркотик|попробуй\s+(герои|кокаи|метамфетамин))", "drugs", "Drug encouragement"),

    # Dangerous health advice
    (r"(?i)(откажись\s+от\s+лекарств|не\s+ходи\s+к\s+врачу|замени\s+лечение)", "health_danger", "Dangerous health advice"),

    # Financial scams
    (r"(?i)(вложи\s+все\s+деньги|отдай\s+сбережения|схема\s+обогащения)", "financial_scam", "Financial scam"),
]

# Words that should trigger a warning (not block, but flag for review)
WARNING_PATTERNS = [
    (r"(?i)(смерт[ьи]|умере[тш]|погибн)", "death_mention", "Death mention"),
    (r"(?i)(болезн[ьи]|тяжел\w+\s+заболевани)", "illness", "Illness mention"),
    (r"(?i)(развод|расставани|измен[аыу])", "relationship_negative", "Negative relationship"),
]


def check_content_safety(text: str) -> tuple[bool, str | None]:
    """Check generated horoscope text for harmful content.

    Returns:
        Tuple of (is_safe, violation_category).
        If is_safe is True, violation_category is None.
        If is_safe is False, violation_category describes the violation.
    """
    if not text:
        return True, None

    for pattern, category, description in BLOCKED_PATTERNS:
        if re.search(pattern, text):
            logger.warning(
                "Content safety BLOCKED: category=%s, description=%s",
                category, description,
            )
            return False, category

    # Check for warnings (log but don't block)
    for pattern, category, description in WARNING_PATTERNS:
        if re.search(pattern, text):
            logger.info(
                "Content safety WARNING: category=%s, description=%s",
                category, description,
            )

    return True, None


# Safety instructions added to the system prompt
SAFETY_SYSTEM_INSTRUCTIONS = """

КРИТИЧЕСКИ ВАЖНЫЕ ОГРАНИЧЕНИЯ (никогда не нарушай):
- НИКОГДА не упоминай и не поощряй суицид, самоповреждение или смерть
- НИКОГДА не предлагай преступные действия или насилие
- НИКОГДА не унижай и не оскорбляй пользователя
- НИКОГДА не давай конкретных медицинских рекомендаций (замени на "обратись к врачу")
- НИКОГДА не давай конкретных финансовых рекомендаций (замени на "проконсультируйся со специалистом")
- НИКОГДА не поощряй употребление наркотиков или алкоголя
- Тон всегда позитивный, поддерживающий и вдохновляющий
- Если тема сложная (здоровье, финансы) - направляй к специалистам
"""
