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
    feedback: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class HoroscopeGenerateRequest(BaseModel):
    """Request to generate a new horoscope."""
    target_date: Optional[str] = None  # ISO format, defaults to today


class HoroscopeFeedbackRequest(BaseModel):
    """Request to submit feedback on a horoscope."""
    feedback: str  # "like" or "dislike"


class HoroscopeHistoryResponse(BaseModel):
    """List of recent horoscopes with feedback."""
    horoscopes: list[HoroscopeResponse]
    total: int
