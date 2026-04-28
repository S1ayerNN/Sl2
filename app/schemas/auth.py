from pydantic import BaseModel
from typing import Optional


class TelegramAuthData(BaseModel):
    """Data received from Telegram Login Widget."""
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str


class GoogleAuthData(BaseModel):
    """Data received from Google Sign-In."""
    id_token: str


class TokenResponse(BaseModel):
    """JWT token pair response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    """Request to refresh access token."""
    refresh_token: str


class UserRegistrationData(BaseModel):
    """Additional data needed during first-time registration."""
    name: str
    birth_date: str  # ISO format: YYYY-MM-DD
    gender: str  # male, female, other

    @classmethod
    def model_validate(cls, *args, **kwargs):
        instance = super().model_validate(*args, **kwargs)
        # Validate name length
        if len(instance.name.strip()) < 2 or len(instance.name.strip()) > 100:
            raise ValueError("Name must be between 2 and 100 characters")
        instance.name = instance.name.strip()
        # Validate gender
        if instance.gender not in ("male", "female", "other"):
            raise ValueError("Gender must be 'male', 'female', or 'other'")
        # Validate birth_date format
        import re
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', instance.birth_date):
            raise ValueError("Birth date must be in YYYY-MM-DD format")
        return instance
