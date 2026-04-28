import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

security_scheme = HTTPBearer()


def create_access_token(user_id: str) -> str:
    """Create a JWT access token."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": user_id,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create a JWT refresh token."""
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = {
        "sub": user_id,
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency that extracts and validates the current user from JWT."""
    payload = decode_token(credentials.credentials)

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return user


def verify_telegram_auth(auth_data: dict, bot_token: str) -> bool:
    """Verify Telegram Login Widget authentication data.

    See: https://core.telegram.org/widgets/login#checking-authorization
    """
    check_hash = auth_data.pop("hash", None)
    if not check_hash:
        return False

    # Sort data alphabetically and create check string
    data_check_arr = sorted(
        [f"{key}={value}" for key, value in auth_data.items()]
    )
    data_check_string = "\n".join(data_check_arr)

    # Create secret key from bot token
    secret_key = hashlib.sha256(bot_token.encode()).digest()

    # Calculate HMAC
    hmac_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    return hmac_hash == check_hash


async def verify_google_token(id_token: str) -> Optional[dict]:
    """Verify Google OAuth2 ID token and return user info."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}"
            )
            if response.status_code != 200:
                return None

            data = response.json()

            # Verify the token is for our app
            if data.get("aud") != settings.GOOGLE_CLIENT_ID:
                return None

            return {
                "google_id": data["sub"],
                "email": data.get("email"),
                "name": data.get("name"),
                "picture": data.get("picture"),
            }
    except Exception:
        return None
