from datetime import date, datetime, time
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class UserProfile(BaseModel):
    """Full user profile response."""
    id: UUID
    name: str
    birth_date: date
    gender: str
    zodiac_sign: str

    # Optional extended profile
    birth_time: Optional[time] = None
    birth_place: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    interests: Optional[dict] = None

    # Subscription
    subscription_tier: str
    subscription_expires: Optional[datetime] = None
    is_premium: bool

    # Meta
    profile_completeness: int
    created_at: datetime

    model_config = {"from_attributes": True}


class UserProfileUpdate(BaseModel):
    """Request to update user profile."""
    name: Optional[str] = None
    birth_time: Optional[str] = None  # HH:MM format
    birth_place: Optional[str] = None
    email: Optional[str] = None
    interests: Optional[dict] = None


class ProfileCompletenessHint(BaseModel):
    """Hint about what fields to fill for better horoscopes."""
    completeness: int
    missing_fields: list[str]
    hint_message: str
