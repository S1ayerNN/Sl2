from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_google_token,
    verify_telegram_auth,
)
from app.core.config import settings
from app.models.user import User
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
    """Authenticate user via Telegram Login.

    If user doesn't exist, creates a new account (requires registration_data).
    """
    # Verify Telegram auth
    auth_dict = auth_data.model_dump()
    telegram_id = str(auth_dict["id"])

    is_valid = verify_telegram_auth(
        auth_dict.copy(), settings.TELEGRAM_BOT_TOKEN
    )
    if not is_valid:
        raise ValueError("Invalid Telegram authentication data")

    # Find existing user
    result = await db.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        # New user - registration required
        if registration_data is None:
            raise ValueError("Registration data required for new users")

        birth_date = date.fromisoformat(registration_data.birth_date)
        zodiac_sign = get_zodiac_sign(birth_date)

        user = User(
            telegram_id=telegram_id,
            name=registration_data.name,
            birth_date=birth_date,
            gender=registration_data.gender,
            zodiac_sign=zodiac_sign,
            avatar_url=auth_data.photo_url,
        )
        user.profile_completeness = user.calculate_completeness()
        db.add(user)
        await db.flush()

    # Generate tokens
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


async def authenticate_google(
    auth_data: GoogleAuthData,
    registration_data: Optional[UserRegistrationData],
    db: AsyncSession,
) -> TokenResponse:
    """Authenticate user via Google Sign-In.

    If user doesn't exist, creates a new account (requires registration_data).
    """
    # Verify Google token
    google_info = await verify_google_token(auth_data.id_token)
    if google_info is None:
        raise ValueError("Invalid Google authentication token")

    google_id = google_info["google_id"]

    # Find existing user
    result = await db.execute(
        select(User).where(User.google_id == google_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        # New user - registration required
        if registration_data is None:
            raise ValueError("Registration data required for new users")

        birth_date = date.fromisoformat(registration_data.birth_date)
        zodiac_sign = get_zodiac_sign(birth_date)

        user = User(
            google_id=google_id,
            name=registration_data.name,
            birth_date=birth_date,
            gender=registration_data.gender,
            zodiac_sign=zodiac_sign,
            email=google_info.get("email"),
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

    # Verify user still exists
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


async def check_user_exists(
    telegram_id: Optional[str] = None,
    google_id: Optional[str] = None,
    db: AsyncSession = None,
) -> bool:
    """Check if a user with given provider ID already exists."""
    if telegram_id:
        result = await db.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
    elif google_id:
        result = await db.execute(
            select(User).where(User.google_id == google_id)
        )
    else:
        return False

    return result.scalar_one_or_none() is not None
