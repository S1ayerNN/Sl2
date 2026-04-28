from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class HoroscopeResponse(BaseModel):
    """Single horoscope response."""
    id: UUID
    horoscope_date: date
    horoscope_text: str
    ai_model_used: str
    horoscope_type: str = "general"
    focus_interest_id: Optional[str] = None
    feedback: Optional[str] = None
    safety_passed: bool = True
    family_member_id: Optional[UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class HoroscopeGenerateRequest(BaseModel):
    """Request to generate a new horoscope.

    User has NO text input fields. Only predefined selections.
    """
    target_date: Optional[str] = None  # ISO format, defaults to today
    family_member_id: Optional[str] = None  # UUID of family member, or None for self
    # Horoscope type: "general" (default), "focused", "regeneration"
    horoscope_type: str = "general"
    # For type="focused": interest ID from catalog (e.g. "love", "career")
    focus_interest_id: Optional[str] = None


class HoroscopeFeedbackRequest(BaseModel):
    """Request to submit feedback on a horoscope."""
    feedback: str  # "like" or "dislike"


class HoroscopeHistoryResponse(BaseModel):
    """List of recent horoscopes with feedback."""
    horoscopes: list[HoroscopeResponse]
    total: int


class AdTokenResponse(BaseModel):
    """Ad token for free users."""
    token: str
    expires_in_seconds: int


class AdConfirmRequest(BaseModel):
    """Confirm ad was viewed."""
    token: str
