from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import cache_horoscope, check_rate_limit, get_cached_horoscope
from app.models.horoscope import Horoscope
from app.models.user import User
from app.services.ai_service import generate_horoscope


async def get_user_history(
    user_id: UUID, db: AsyncSession, limit: int = 5
) -> list[Horoscope]:
    """Get the last N horoscopes for a user (with feedback)."""
    result = await db.execute(
        select(Horoscope)
        .where(Horoscope.user_id == user_id)
        .order_by(desc(Horoscope.created_at))
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_todays_horoscope(
    user: User, db: AsyncSession
) -> Horoscope | None:
    """Check if user already has a horoscope for today."""
    today = date.today()
    result = await db.execute(
        select(Horoscope)
        .where(Horoscope.user_id == user.id)
        .where(Horoscope.horoscope_date == today)
        .order_by(desc(Horoscope.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_horoscope(
    user: User,
    db: AsyncSession,
    target_date: date | None = None,
) -> Horoscope:
    """Generate and save a new horoscope for the user.

    Handles rate limiting, caching, history lookup, and AI generation.
    """
    if target_date is None:
        target_date = date.today()

    # Check rate limit
    daily_limit = (
        settings.HOROSCOPE_DAILY_LIMIT_PREMIUM
        if user.is_premium
        else settings.HOROSCOPE_DAILY_LIMIT_FREE
    )
    within_limit = await check_rate_limit(str(user.id), daily_limit)
    if not within_limit:
        raise ValueError(
            f"Daily horoscope limit reached ({daily_limit}). "
            "Upgrade to premium for more horoscopes!"
        )

    # Check cache
    cached = await get_cached_horoscope(str(user.id), target_date.isoformat())
    if cached:
        # Return existing horoscope from cache
        existing = await get_todays_horoscope(user, db)
        if existing:
            return existing

    # Get history for personalization
    history = await get_user_history(
        user.id, db, limit=settings.HOROSCOPE_HISTORY_SIZE
    )

    # Generate via AI
    horoscope_text, prompt_used, model_used = await generate_horoscope(
        user=user,
        target_date=target_date,
        history=history,
        is_premium=user.is_premium,
    )

    # Save to database
    horoscope = Horoscope(
        user_id=user.id,
        horoscope_date=target_date,
        horoscope_text=horoscope_text,
        ai_model_used=model_used,
        prompt_used=prompt_used,
    )
    db.add(horoscope)
    await db.flush()

    # Cache the result
    await cache_horoscope(str(user.id), target_date.isoformat(), horoscope_text)

    # Cleanup old horoscopes (keep only last HOROSCOPE_HISTORY_SIZE)
    await _cleanup_old_horoscopes(user.id, db)

    return horoscope


async def submit_feedback(
    horoscope_id: UUID, user_id: UUID, feedback: str, db: AsyncSession
) -> Horoscope:
    """Submit feedback (like/dislike) for a horoscope."""
    if feedback not in ("like", "dislike"):
        raise ValueError("Feedback must be 'like' or 'dislike'")

    result = await db.execute(
        select(Horoscope)
        .where(Horoscope.id == horoscope_id)
        .where(Horoscope.user_id == user_id)
    )
    horoscope = result.scalar_one_or_none()

    if horoscope is None:
        raise ValueError("Horoscope not found")

    horoscope.feedback = feedback
    await db.flush()

    return horoscope


async def _cleanup_old_horoscopes(user_id: UUID, db: AsyncSession) -> None:
    """Keep only the last HOROSCOPE_HISTORY_SIZE horoscopes per user."""
    # Count total horoscopes
    count_result = await db.execute(
        select(func.count(Horoscope.id)).where(Horoscope.user_id == user_id)
    )
    total = count_result.scalar()

    max_keep = settings.HOROSCOPE_HISTORY_SIZE
    if total <= max_keep:
        return

    # Get IDs to keep (most recent)
    keep_result = await db.execute(
        select(Horoscope.id)
        .where(Horoscope.user_id == user_id)
        .order_by(desc(Horoscope.created_at))
        .limit(max_keep)
    )
    keep_ids = [row[0] for row in keep_result.all()]

    # Delete the rest
    from sqlalchemy import delete

    await db.execute(
        delete(Horoscope)
        .where(Horoscope.user_id == user_id)
        .where(Horoscope.id.notin_(keep_ids))
    )
