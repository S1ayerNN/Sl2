"""Horoscope business logic service.

Handles generation, caching, rate limiting, ad verification, and feedback.
All AI interaction happens server-side - users cannot input prompt text.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import select, desc, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import cache_horoscope, check_rate_limit, get_cached_horoscope
from app.models.horoscope import Horoscope
from app.models.user import User, FamilyMember
from app.services.ai_service import (
    generate_horoscope_for_user,
    generate_horoscope_for_family_member,
)
from app.services.ad_service import verify_ad_requirement


async def get_user_history(
    user_id: UUID,
    db: AsyncSession,
    limit: int = 5,
    family_member_id: UUID = None,
) -> list[Horoscope]:
    """Get the last N horoscopes for a user or family member."""
    query = select(Horoscope).where(Horoscope.user_id == user_id)

    if family_member_id:
        query = query.where(Horoscope.family_member_id == family_member_id)
    else:
        query = query.where(Horoscope.family_member_id.is_(None))

    result = await db.execute(
        query.order_by(desc(Horoscope.created_at)).limit(limit)
    )
    return list(result.scalars().all())


async def get_todays_horoscope(
    user: User,
    db: AsyncSession,
    family_member_id: UUID = None,
) -> Horoscope | None:
    """Check if user already has a horoscope for today."""
    today = date.today()
    query = (
        select(Horoscope)
        .where(Horoscope.user_id == user.id)
        .where(Horoscope.horoscope_date == today)
    )

    if family_member_id:
        query = query.where(Horoscope.family_member_id == family_member_id)
    else:
        query = query.where(Horoscope.family_member_id.is_(None))

    result = await db.execute(
        query.order_by(desc(Horoscope.created_at)).limit(1)
    )
    return result.scalar_one_or_none()


async def create_horoscope(
    user: User,
    db: AsyncSession,
    target_date: date | None = None,
    family_member_id: UUID | None = None,
) -> Horoscope:
    """Generate and save a new horoscope.

    For free users: requires ad verification for each generation.
    """
    if target_date is None:
        target_date = date.today()

    # Ad verification for free users
    if not user.is_premium:
        ad_ok = await verify_ad_requirement(user)
        if not ad_ok:
            raise ValueError(
                "Ad viewing required. Request an ad token, watch the ad, "
                "then confirm before generating a horoscope."
            )

    # Rate limit check
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

    # Resolve family member if specified
    member = None
    if family_member_id:
        result = await db.execute(
            select(FamilyMember)
            .where(FamilyMember.id == family_member_id)
            .where(FamilyMember.owner_id == user.id)
        )
        member = result.scalar_one_or_none()
        if member is None:
            raise ValueError("Family member not found")

    # Get history for personalization
    history = await get_user_history(
        user.id, db,
        limit=settings.HOROSCOPE_HISTORY_SIZE,
        family_member_id=family_member_id,
    )

    # Generate via AI (all prompt building is server-side)
    if member:
        text, prompt, model, safety_ok = await generate_horoscope_for_family_member(
            member=member,
            target_date=target_date,
            history=history,
            is_premium=user.is_premium,
        )
    else:
        text, prompt, model, safety_ok = await generate_horoscope_for_user(
            user=user,
            target_date=target_date,
            history=history,
            is_premium=user.is_premium,
        )

    # Save to database
    horoscope = Horoscope(
        user_id=user.id,
        family_member_id=family_member_id,
        horoscope_date=target_date,
        horoscope_text=text,
        ai_model_used=model,
        prompt_used=prompt,
        safety_passed=safety_ok,
    )
    db.add(horoscope)
    await db.flush()

    # Cache the result
    cache_key = f"{user.id}:{family_member_id or 'self'}"
    await cache_horoscope(cache_key, target_date.isoformat(), text)

    # Cleanup old horoscopes
    await _cleanup_old_horoscopes(user.id, db, family_member_id)

    # Invalidate ad token after successful generation (one horoscope per ad)
    if not user.is_premium:
        user.ad_view_token = None
        await db.flush()

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


async def _cleanup_old_horoscopes(
    user_id: UUID,
    db: AsyncSession,
    family_member_id: UUID = None,
) -> None:
    """Keep only the last HOROSCOPE_HISTORY_SIZE horoscopes."""
    query = select(func.count(Horoscope.id)).where(Horoscope.user_id == user_id)
    if family_member_id:
        query = query.where(Horoscope.family_member_id == family_member_id)
    else:
        query = query.where(Horoscope.family_member_id.is_(None))

    count_result = await db.execute(query)
    total = count_result.scalar()

    max_keep = settings.HOROSCOPE_HISTORY_SIZE
    if total <= max_keep:
        return

    keep_query = (
        select(Horoscope.id)
        .where(Horoscope.user_id == user_id)
    )
    if family_member_id:
        keep_query = keep_query.where(Horoscope.family_member_id == family_member_id)
    else:
        keep_query = keep_query.where(Horoscope.family_member_id.is_(None))

    keep_result = await db.execute(
        keep_query.order_by(desc(Horoscope.created_at)).limit(max_keep)
    )
    keep_ids = [row[0] for row in keep_result.all()]

    del_query = (
        delete(Horoscope)
        .where(Horoscope.user_id == user_id)
        .where(Horoscope.id.notin_(keep_ids))
    )
    if family_member_id:
        del_query = del_query.where(Horoscope.family_member_id == family_member_id)
    else:
        del_query = del_query.where(Horoscope.family_member_id.is_(None))

    await db.execute(del_query)
