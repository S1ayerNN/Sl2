from datetime import date, datetime, time
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.models.user import InterestCategory, Gender, FamilyRelation


# Predefined lists for frontend dropdowns
AVAILABLE_INTERESTS = [
    {"value": ic.value, "label_ru": label}
    for ic, label in {
        InterestCategory.LOVE: "Любовь и отношения",
        InterestCategory.CAREER: "Карьера и работа",
        InterestCategory.HEALTH: "Здоровье",
        InterestCategory.FINANCE: "Финансы",
        InterestCategory.FAMILY: "Семья",
        InterestCategory.EDUCATION: "Образование и развитие",
        InterestCategory.TRAVEL: "Путешествия",
        InterestCategory.CREATIVITY: "Творчество",
    }.items()
]

AVAILABLE_GENDERS = [
    {"value": g.value, "label_ru": label}
    for g, label in {
        Gender.MALE: "Мужской",
        Gender.FEMALE: "Женский",
        Gender.OTHER: "Другой",
    }.items()
]

AVAILABLE_RELATIONS = [
    {"value": r.value, "label_ru": label}
    for r, label in {
        FamilyRelation.SPOUSE: "Супруг(а)",
        FamilyRelation.CHILD: "Ребенок",
        FamilyRelation.PARENT: "Родитель",
        FamilyRelation.SIBLING: "Брат/Сестра",
        FamilyRelation.PARTNER: "Партнер",
    }.items()
]


class UserProfile(BaseModel):
    """User profile response (PII is decrypted before returning)."""
    id: UUID
    name: str  # Decrypted
    birth_date: date
    gender: str
    zodiac_sign: str

    # Optional extended profile (decrypted)
    birth_time: Optional[time] = None
    birth_place: Optional[str] = None  # Decrypted
    email: Optional[str] = None  # Decrypted
    avatar_url: Optional[str] = None

    # Interests - only predefined categories
    interests: list[str] = []

    # Subscription
    subscription_tier: str
    subscription_expires: Optional[datetime] = None
    is_premium: bool

    # Family
    family_members_count: int = 0
    family_members_limit: int = 0

    # Meta
    profile_completeness: int
    created_at: datetime


class UserProfileUpdate(BaseModel):
    """Request to update user profile. Only predefined values accepted."""
    name: Optional[str] = None
    birth_time: Optional[str] = None  # HH:MM format
    birth_place: Optional[str] = None
    email: Optional[str] = None
    # Interests MUST be from InterestCategory enum
    interests: Optional[list[str]] = None


class ProfileCompletenessHint(BaseModel):
    """Hint about what fields to fill for better horoscopes."""
    completeness: int
    missing_fields: list[str]
    hint_message: str


class AvailableOptionsResponse(BaseModel):
    """Predefined options for frontend dropdowns."""
    interests: list[dict]
    genders: list[dict]
    relations: list[dict]


class FamilyMemberCreate(BaseModel):
    """Create a family member profile."""
    name: str
    relation: str  # FamilyRelation enum value
    birth_date: str  # YYYY-MM-DD
    gender: str  # Gender enum value
    birth_time: Optional[str] = None  # HH:MM
    interests: Optional[list[str]] = None


class FamilyMemberResponse(BaseModel):
    """Family member profile response."""
    id: UUID
    name: str  # Decrypted
    relation: str
    birth_date: date
    birth_time: Optional[time] = None
    gender: str
    zodiac_sign: str
    interests: list[str] = []
    created_at: datetime
