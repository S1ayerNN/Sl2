from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.auth import (
    GoogleAuthData,
    RefreshTokenRequest,
    TelegramAuthData,
    TokenResponse,
    UserRegistrationData,
)
from app.core.config import settings
from app.services.auth_service import (
    authenticate_google,
    authenticate_telegram,
    refresh_tokens,
)
from app.services.zodiac_service import get_zodiac_sign
from app.core.crypto import encrypt_pii
from app.core.security import create_access_token, create_refresh_token
from app.models.user import User
from sqlalchemy import select
from datetime import date

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/telegram", response_model=TokenResponse)
async def login_telegram(
    auth_data: TelegramAuthData,
    registration_data: UserRegistrationData | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate via Telegram Login Widget.

    For new users, `registration_data` (name, birth_date, gender) is required.
    For existing users, only `auth_data` is needed.
    """
    try:
        return await authenticate_telegram(auth_data, registration_data, db)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/google", response_model=TokenResponse)
async def login_google(
    auth_data: GoogleAuthData,
    registration_data: UserRegistrationData | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate via Google Sign-In.

    For new users, `registration_data` (name, birth_date, gender) is required.
    For existing users, only `auth_data` (id_token) is needed.
    """
    try:
        return await authenticate_google(auth_data, registration_data, db)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token using a valid refresh token."""
    try:
        return await refresh_tokens(request.refresh_token, db)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


# --- Dev/Test Login (only available when DEBUG=true) ---


from pydantic import BaseModel


class DevLoginRequest(BaseModel):
    """Quick login for development/testing. Creates a test user if needed."""
    name: str = "Test User"
    birth_date: str = "1995-03-15"
    gender: str = "male"


@router.post("/dev-login", response_model=TokenResponse)
async def dev_login(
    request: DevLoginRequest = DevLoginRequest(),
    db: AsyncSession = Depends(get_db),
):
    """Development-only login. Creates/finds a test user and returns tokens.

    Only available when DEBUG=true. DO NOT use in production.
    """
    if not settings.DEBUG:
        raise HTTPException(status_code=403, detail="Dev login only available in DEBUG mode")

    # Use a fixed test telegram_id
    test_telegram_id = "dev_test_user_12345"

    result = await db.execute(
        select(User).where(User.telegram_id == test_telegram_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        birth = date.fromisoformat(request.birth_date)
        user = User(
            telegram_id=test_telegram_id,
            name_encrypted=encrypt_pii(request.name),
            birth_date=birth,
            gender=request.gender,
            zodiac_sign=get_zodiac_sign(birth),
            interests=["love", "career", "health"],
        )
        user.profile_completeness = user.calculate_completeness()
        db.add(user)
        await db.flush()

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )
