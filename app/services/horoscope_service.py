"""Horoscope business logic service.

Uses tier_config for all limits and feature flags.
Supports 3 horoscope types: general, focused (by interest), regeneration.
Free tier: unlimited general horoscopes (ad-gated), no focus/regen.
Plus/Premium: limited by daily counters, with focus and regeneration.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import select, desc, func, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import cache_horoscope, get_cached_horoscope, redis_client
from app.models.horoscope import Horoscope
from app.models.user import User, FamilyMember
from app.services.ai_service import (
    generate_horoscope_for_user,
    generate_horoscope_for_family_member,
)
from app.services.ad_service import verify_ad_requirement
from app.services.interest_catalog import get_interest_by_id
from app.services.tier_config import get_tier_config


async def _check_daily_counter(user_id: str, counter_type: str, limit: int) -> bool:
    """Check and increment a daily counter in Redis.

    counter_type: "general", "focus", "regen"
    limit: 0 = unlimited
    Returns True if within limit.
    """
    if limit == 0:
        return True  # Unlimited

    key = f"daily:{counter_type}:{user_id}"
    try:
        current = await redis_client.incr(key)
        if current == 1:
            await redis_client.expire(key, 86400)
        return current <= limit
    except Exception:
        return False  # Fail closed


async def get_user_history(
    user_id: UUID,
    db: AsyncSession,
    limit: int = 5,
    family_member_id: UUID = None,
    horoscope_type: str = "general",
) -> list[Horoscope]:
    """Get recent horoscopes for prompt context."""
    query = (
        select(Horoscope)
        .where(Horoscope.user_id == user_id)
        .where(Horoscope.horoscope_type.in_(["general", "focused"]))  # Both types inform AI
    )
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
    horoscope_type: str = "general",
) -> Horoscope | None:
    """Check if user already has a horoscope for today."""
    today = date.today()
    query = (
        select(Horoscope)
        .where(Horoscope.user_id == user.id)
        .where(Horoscope.horoscope_date == today)
        .where(Horoscope.horoscope_type == horoscope_type)
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
    horoscope_type: str = "general",
    focus_interest_id: str | None = None,
) -> Horoscope:
    """Generate and save a horoscope.

    Enforces tier-based limits:
    - Free: unlimited general (with ad), no focus/regen
    - Plus: 3 general + 1 focus + 1 regen per day
    - Premium: 6 general + 2 focus + 3 regen per day
    """
    if target_date is None:
        target_date = date.today()

    # Get tier configuration
    tier = get_tier_config(user.subscription_tier)

    # --- Permission checks ---

    # Focus sphere check
    if horoscope_type == "focused":
        if not tier.focus_sphere_enabled:
            raise ValueError(
                "Focused horoscopes are available for Plus and Premium subscribers."
            )
        if not focus_interest_id:
            raise ValueError("focus_interest_id is required for focused horoscopes.")
        interest = get_interest_by_id(focus_interest_id)
        if not interest or not interest.active:
            raise ValueError(f"Invalid interest: {focus_interest_id}")

    # Family member check
    if family_member_id:
        if tier.family_members_limit == 0:
            raise ValueError("Family horoscopes are available for Plus and Premium subscribers.")

    # Ad verification for free users (every general horoscope)
    if tier.ads_required and horoscope_type == "general":
        ad_ok = await verify_ad_requirement(user)
        if not ad_ok:
            raise ValueError(
                "Watch an ad to get your horoscope. "
                "Request token: POST /ads/request-token"
            )

    # --- Rate limit checks (per type) ---
    user_key = str(user.id)

    if horoscope_type == "general":
        within = await _check_daily_counter(user_key, "general", tier.daily_general_limit)
        if not within:
            raise ValueError(
                f"Daily general horoscope limit reached ({tier.daily_general_limit}). "
                "Upgrade your plan for more!"
            )

    elif horoscope_type == "focused":
        within = await _check_daily_counter(user_key, "focus", tier.daily_focus_limit)
        if not within:
            raise ValueError(
                f"Daily focused horoscope limit reached ({tier.daily_focus_limit})."
            )

    elif horoscope_type == "regeneration":
        if tier.regeneration_limit == 0:
            raise ValueError("Regeneration is available for Plus and Premium subscribers.")
        within = await _check_daily_counter(user_key, "regen", tier.regeneration_limit)
        if not within:
            raise ValueError(
                f"Daily regeneration limit reached ({tier.regeneration_limit})."
            )

    # --- Resolve family member ---
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

    # --- Get history (tier-controlled depth) ---
    history = await get_user_history(
        user.id, db,
        limit=tier.history_in_prompt,
        family_member_id=family_member_id,
    )

    # --- Generate ---
    if member:
        text, prompt, model, safety_ok = await generate_horoscope_for_family_member(
            member=member,
            target_date=target_date,
            history=history,
            is_premium=(tier.tier_id == "premium"),
        )
    else:
        text, prompt, model, safety_ok = await generate_horoscope_for_user(
            user=user,
            target_date=target_date,
            history=history,
            is_premium=(tier.tier_id == "premium"),
        )

    # --- Save ---
    horoscope = Horoscope(
        user_id=user.id,
        family_member_id=family_member_id,
        horoscope_type=horoscope_type,
        focus_interest_id=focus_interest_id,
        horoscope_date=target_date,
        horoscope_text=text,
        ai_model_used=model,
        prompt_used=prompt,
        safety_passed=safety_ok,
    )
    db.add(horoscope)
    await db.flush()

    # Cache
    cache_key = f"{user.id}:{family_member_id or 'self'}:{horoscope_type}"
    await cache_horoscope(cache_key, target_date.isoformat(), text)

    # Cleanup old (keep last HOROSCOPE_HISTORY_SIZE per type per person)
    await _cleanup_old_horoscopes(user.id, db, family_member_id)

    # Invalidate ad token after generation (free users)
    if tier.ads_required and horoscope_type == "general":
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
    user_id: UUID, db: AsyncSession, family_member_id: UUID = None,
) -> None:
    """Keep only the last N horoscopes per person (across all types)."""
    filters = [Horoscope.user_id == user_id]
    if family_member_id:
        filters.append(Horoscope.family_member_id == family_member_id)
    else:
        filters.append(Horoscope.family_member_id.is_(None))

    count_result = await db.execute(
        select(func.count(Horoscope.id)).where(and_(*filters))
    )
    total = count_result.scalar()

    max_keep = settings.HOROSCOPE_HISTORY_SIZE
    if total <= max_keep:
        return

    keep_result = await db.execute(
        select(Horoscope.id)
        .where(and_(*filters))
        .order_by(desc(Horoscope.created_at))
        .limit(max_keep)
    )
    keep_ids = [row[0] for row in keep_result.all()]

    await db.execute(
        delete(Horoscope)
        .where(and_(*filters))
        .where(Horoscope.id.notin_(keep_ids))
    )
