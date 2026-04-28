import hashlib
import hmac
import re
import time as time_module
import uuid as uuid_module
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

# Maximum allowed age for Telegram auth data (seconds)
TELEGRAM_AUTH_MAX_AGE = 300  # 5 minutes


def _ensure_secret_key() -> str:
    """Ensure JWT secret key is not the default placeholder."""
    if settings.JWT_SECRET_KEY == "change-me-to-a-random-secret-key":
        raise RuntimeError(
            "CRITICAL: JWT_SECRET_KEY is set to the default value. "
            "Set a strong random secret in .env before running the app."
        )
    return settings.JWT_SECRET_KEY


def create_access_token(user_id: str) -> str:
    """Create a JWT access token."""
    secret = _ensure_secret_key()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": user_id,
        "exp": expire,
        "type": "access",
        "jti": str(uuid_module.uuid4()),  # Unique token ID
    }
    return jwt.encode(payload, secret, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create a JWT refresh token with unique ID for revocation support."""
    secret = _ensure_secret_key()
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = {
        "sub": user_id,
        "exp": expire,
        "type": "refresh",
        "jti": str(uuid_module.uuid4()),  # Unique token ID for blacklisting
    }
    return jwt.encode(payload, secret, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        secret = _ensure_secret_key()
        payload = jwt.decode(
            token, secret, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


async def is_token_blacklisted(jti: str) -> bool:
    """Check if a token has been revoked (blacklisted in Redis)."""
    from app.core.redis import redis_client
    return await redis_client.exists(f"token_blacklist:{jti}") > 0


async def blacklist_token(jti: str, ttl_seconds: int) -> None:
    """Add a token to the blacklist (revoke it)."""
    from app.core.redis import redis_client
    await redis_client.setex(f"token_blacklist:{jti}", ttl_seconds, "revoked")


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

    # Check token blacklist
    jti = payload.get("jti")
    if jti and await is_token_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    # Validate UUID format before DB query
    try:
        parsed_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    result = await db.execute(select(User).where(User.id == parsed_uuid))
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

    Security checks:
    - HMAC signature verification
    - auth_date freshness (max 5 minutes old)
    """
    check_hash = auth_data.pop("hash", None)
    if not check_hash:
        return False

    # Verify auth_date is not too old (replay attack protection)
    auth_date = auth_data.get("auth_date")
    if auth_date is not None:
        try:
            auth_timestamp = int(auth_date)
            current_timestamp = int(time_module.time())
            if current_timestamp - auth_timestamp > TELEGRAM_AUTH_MAX_AGE:
                return False
        except (ValueError, TypeError):
            return False

    # Filter out None values before building check string
    filtered_data = {k: v for k, v in auth_data.items() if v is not None}

    # Sort data alphabetically and create check string
    data_check_arr = sorted(
        [f"{key}={value}" for key, value in filtered_data.items()]
    )
    data_check_string = "\n".join(data_check_arr)

    # Create secret key from bot token
    secret_key = hashlib.sha256(bot_token.encode()).digest()

    # Calculate HMAC using constant-time comparison
    hmac_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(hmac_hash, check_hash)


async def verify_google_token(id_token: str) -> Optional[dict]:
    """Verify Google OAuth2 ID token and return user info.

    Uses Google's tokeninfo endpoint with proper validation.
    """
    # Basic input validation - token should be a JWT-like string
    if not id_token or len(id_token) > 4096 or not re.match(r'^[\w\-\.]+$', id_token):
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": id_token},
            )
            if response.status_code != 200:
                return None

            data = response.json()

            # Verify the token is for our app
            if data.get("aud") != settings.GOOGLE_CLIENT_ID:
                return None

            # Verify email is verified
            if data.get("email_verified") != "true":
                return None

            # Verify token is not expired
            exp = data.get("exp")
            if exp and int(exp) < int(time_module.time()):
                return None

            return {
                "google_id": data["sub"],
                "email": data.get("email"),
                "name": data.get("name"),
                "picture": data.get("picture"),
            }
    except Exception:
        return None


def sanitize_for_prompt(text: str, max_length: int = 200) -> str:
    """Sanitize user input before including in AI prompts.

    Strips potentially malicious instruction-injection patterns.
    """
    if not text:
        return ""

    # Truncate to max length
    text = text[:max_length]

    # Remove common prompt injection patterns
    injection_patterns = [
        r"(?i)ignore\s+(all\s+)?previous\s+instructions",
        r"(?i)system\s*prompt",
        r"(?i)you\s+are\s+now",
        r"(?i)forget\s+(all|everything)",
        r"(?i)new\s+instructions?",
        r"(?i)override",
        r"(?i)disregard",
        r"(?i)\bact\s+as\b",
        r"(?i)pretend\s+to\s+be",
    ]

    for pattern in injection_patterns:
        text = re.sub(pattern, "[filtered]", text)

    # Remove control characters
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    return text.strip()
