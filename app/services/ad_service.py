"""Ad verification service for free users.

Free users must watch a rewarded video ad before each horoscope generation.
The flow:
1. Client requests an ad token: POST /api/v1/ads/request-token
2. Client shows the ad (AdMob Rewarded Video)
3. Client confirms ad completion with the token: POST /api/v1/ads/confirm
4. Client generates horoscope (token is verified server-side)

This prevents bypassing ads by manipulating the client.
"""

import secrets
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import redis_client
from app.models.user import User


async def create_ad_token(user_id: str) -> str:
    """Create a one-time ad viewing token for a user.

    Token is stored in Redis with a short TTL.
    Must be confirmed after ad is watched.
    """
    token = secrets.token_hex(32)
    key = f"ad_token:{user_id}:{token}"
    # Store as "pending" - not yet confirmed
    await redis_client.setex(key, settings.AD_VIEW_TOKEN_TTL_SECONDS, "pending")
    return token


async def confirm_ad_viewed(user_id: str, token: str, db: AsyncSession, user: User) -> bool:
    """Confirm that a user has watched an ad.

    Marks the token as confirmed and updates user's last_ad_viewed_at.
    Returns True if confirmed successfully.
    """
    key = f"ad_token:{user_id}:{token}"
    status = await redis_client.get(key)

    if status is None:
        return False  # Token expired or doesn't exist

    if status == "confirmed":
        return False  # Token already used

    # Mark as confirmed (one-time use)
    await redis_client.setex(key, settings.AD_VIEW_TOKEN_TTL_SECONDS, "confirmed")

    # Update user's last ad viewed timestamp
    user.last_ad_viewed_at = datetime.now(timezone.utc)
    user.ad_view_token = token
    await db.flush()

    return True


async def verify_ad_requirement(user: User) -> bool:
    """Check if a free user has watched an ad recently enough to generate a horoscope.

    Premium users bypass this check entirely.
    Returns True if the user can generate a horoscope.
    """
    if user.is_premium:
        return True  # Premium users don't need ads

    if user.ad_view_token is None:
        return False  # No ad token ever set

    # Verify the token is confirmed in Redis
    key = f"ad_token:{str(user.id)}:{user.ad_view_token}"
    status = await redis_client.get(key)

    return status == "confirmed"
