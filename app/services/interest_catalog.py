"""Configurable interest categories catalog.

Interest tags are not hardcoded - they can be added/changed via this catalog
without code changes. The catalog is loaded at startup and cached.

To add a new interest:
1. Add it to INTEREST_CATALOG below
2. Restart the app (or call reload_catalog() via admin API later)

Existing user interests with removed tags will be gracefully ignored.
"""

from dataclasses import dataclass


@dataclass
class InterestTag:
    """Single interest tag definition."""
    id: str           # Unique identifier (stored in DB)
    label_ru: str     # Display name in Russian
    label_en: str     # Display name in English (for future i18n)
    icon: str         # Emoji icon for UI
    prompt_hint: str  # How this interest is described in AI prompt
    active: bool = True  # Can be deactivated without removing


# Master catalog of all available interest tags
# This is the single source of truth for what users can select
INTEREST_CATALOG: list[InterestTag] = [
    InterestTag(
        id="love",
        label_ru="Любовь и отношения",
        label_en="Love & Relationships",
        icon="❤️",
        prompt_hint="романтические отношения, любовь, партнерство",
    ),
    InterestTag(
        id="career",
        label_ru="Карьера и работа",
        label_en="Career & Work",
        icon="💼",
        prompt_hint="карьера, профессиональный рост, рабочие проекты",
    ),
    InterestTag(
        id="health",
        label_ru="Здоровье",
        label_en="Health",
        icon="🏥",
        prompt_hint="физическое и ментальное здоровье, самочувствие, энергия",
    ),
    InterestTag(
        id="finance",
        label_ru="Финансы",
        label_en="Finance",
        icon="💰",
        prompt_hint="финансы, доходы, инвестиции, материальное благополучие",
    ),
    InterestTag(
        id="family",
        label_ru="Семья",
        label_en="Family",
        icon="👨‍👩‍👧‍👦",
        prompt_hint="семейные отношения, дети, родители, домашний очаг",
    ),
    InterestTag(
        id="education",
        label_ru="Образование и развитие",
        label_en="Education & Growth",
        icon="📚",
        prompt_hint="обучение, саморазвитие, новые знания и навыки",
    ),
    InterestTag(
        id="travel",
        label_ru="Путешествия",
        label_en="Travel",
        icon="✈️",
        prompt_hint="путешествия, переезды, новые места, приключения",
    ),
    InterestTag(
        id="creativity",
        label_ru="Творчество",
        label_en="Creativity",
        icon="🎨",
        prompt_hint="творческое самовыражение, искусство, хобби, вдохновение",
    ),
    InterestTag(
        id="friendship",
        label_ru="Дружба и общение",
        label_en="Friendship & Social",
        icon="🤝",
        prompt_hint="дружба, социальные связи, общение, нетворкинг",
    ),
    InterestTag(
        id="spirituality",
        label_ru="Духовность",
        label_en="Spirituality",
        icon="🧘",
        prompt_hint="духовное развитие, медитация, внутренний мир, гармония",
    ),
]

# Build lookup indexes
_catalog_by_id: dict[str, InterestTag] = {t.id: t for t in INTEREST_CATALOG}


def get_active_interests() -> list[InterestTag]:
    """Get all currently active interest tags."""
    return [t for t in INTEREST_CATALOG if t.active]


def get_interest_by_id(interest_id: str) -> InterestTag | None:
    """Look up an interest tag by ID."""
    return _catalog_by_id.get(interest_id)


def validate_interest_ids(ids: list[str]) -> list[str]:
    """Filter a list of interest IDs to only valid, active ones."""
    active_ids = {t.id for t in INTEREST_CATALOG if t.active}
    return [i for i in ids if i in active_ids]


def get_prompt_hints_for_interests(ids: list[str]) -> list[str]:
    """Get AI prompt hints for a list of interest IDs."""
    hints = []
    for interest_id in ids:
        tag = _catalog_by_id.get(interest_id)
        if tag and tag.active:
            hints.append(tag.prompt_hint)
    return hints


def get_catalog_for_api() -> list[dict]:
    """Get the catalog formatted for API response (frontend dropdowns)."""
    return [
        {
            "id": t.id,
            "label_ru": t.label_ru,
            "label_en": t.label_en,
            "icon": t.icon,
        }
        for t in INTEREST_CATALOG
        if t.active
    ]
