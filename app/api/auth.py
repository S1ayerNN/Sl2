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
from app.services.auth_service import (
    authenticate_google,
    authenticate_telegram,
    refresh_tokens,
)

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
