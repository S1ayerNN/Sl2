"""Authentication service.

No authentication credentials are stored in our DB.
Only external provider IDs (telegram_id, google_id) are kept.
User PII (name, email) is encrypted before storage.
"""

from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_pii, hash_identifier
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_google_token,
    verify_telegram_auth,
)
from app.core.config import settings
from app.models.user import User, Gender
from app.schemas.auth import (
    TelegramAuthData,
    GoogleAuthData,
    TokenResponse,
    UserRegistrationData,
)
from app.services.zodiac_service import get_zodiac_sign


async def authenticate_telegram(
    auth_data: TelegramAuthData,
    registration_data: Optional[UserRegistrationData],
    db: AsyncSession,
) -> TokenResponse:
    """Authenticate user via Telegram Login."""
    auth_dict = auth_data.model_dump()
    telegram_id = str(auth_dict["id"])

    is_valid = verify_telegram_auth(
        auth_dict.copy(), settings.TELEGRAM_BOT_TOKEN
    )
    if not is_valid:
        raise ValueError("Invalid Telegram authentication data")

    result = await db.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        if registration_data is None:
            raise ValueError("Registration data required for new users")

        # Validate gender
        if registration_data.gender not in [g.value for g in Gender]:
            raise ValueError("Invalid gender value")

        birth_date = date.fromisoformat(registration_data.birth_date)
        zodiac_sign = get_zodiac_sign(birth_date)

        user = User(
            telegram_id=telegram_id,
            # PII is encrypted before storage
            name_encrypted=encrypt_pii(registration_data.name),
            birth_date=birth_date,
            gender=registration_data.gender,
            zodiac_sign=zodiac_sign,
            avatar_url=auth_data.photo_url,
        )
        user.profile_completeness = user.calculate_completeness()
        db.add(user)
        await db.flush()

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


async def authenticate_google(
    auth_data: GoogleAuthData,
    registration_data: Optional[UserRegistrationData],
    db: AsyncSession,
) -> TokenResponse:
    """Authenticate user via Google Sign-In."""
    google_info = await verify_google_token(auth_data.id_token)
    if google_info is None:
        raise ValueError("Invalid Google authentication token")

    google_id = google_info["google_id"]

    result = await db.execute(
        select(User).where(User.google_id == google_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        if registration_data is None:
            raise ValueError("Registration data required for new users")

        if registration_data.gender not in [g.value for g in Gender]:
            raise ValueError("Invalid gender value")

        birth_date = date.fromisoformat(registration_data.birth_date)
        zodiac_sign = get_zodiac_sign(birth_date)

        email = google_info.get("email")

        user = User(
            google_id=google_id,
            name_encrypted=encrypt_pii(registration_data.name),
            birth_date=birth_date,
            gender=registration_data.gender,
            zodiac_sign=zodiac_sign,
            email_encrypted=encrypt_pii(email) if email else None,
            email_hash=hash_identifier(email) if email else None,
            avatar_url=google_info.get("picture"),
        )
        user.profile_completeness = user.calculate_completeness()
        db.add(user)
        await db.flush()

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


async def refresh_tokens(refresh_token: str, db: AsyncSession) -> TokenResponse:
    """Generate new token pair from refresh token."""
    payload = decode_token(refresh_token)

    if payload.get("type") != "refresh":
        raise ValueError("Invalid token type")

    user_id = payload.get("sub")

    result = await db.execute(
        select(User).where(User.id == UUID(user_id))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError("User not found")

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )
