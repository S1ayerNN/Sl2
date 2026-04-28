"""Horoscope API endpoints.

Users have NO text input for AI prompts. They can only:
- Select horoscope type: general, focused (by predefined interest), regeneration
- Optionally target a family member
- View history and submit feedback
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.horoscope import (
    HoroscopeFeedbackRequest,
    HoroscopeGenerateRequest,
    HoroscopeHistoryResponse,
    HoroscopeResponse,
)
from app.services.horoscope_service import (
    create_horoscope,
    get_todays_horoscope,
    get_user_history,
    submit_feedback,
)
from app.services.tier_config import get_tier_config

router = APIRouter(prefix="/horoscope", tags=["Horoscope"])


@router.post("/generate", response_model=HoroscopeResponse)
async def generate_horoscope(
    request: HoroscopeGenerateRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a personalized horoscope.

    Types:
    - "general": standard daily horoscope (free: ad required)
    - "focused": horoscope focused on a specific interest (Plus/Premium only)
    - "regeneration": re-generate a horoscope you didn't like (Plus/Premium only)

    User has NO text input - everything is from profile and predefined selections.
    """
    target_date = None
    family_member_id = None
    horoscope_type = "general"
    focus_interest_id = None

    if request:
        if request.target_date:
            try:
                target_date = date.fromisoformat(request.target_date)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        if request.family_member_id:
            try:
                family_member_id = UUID(request.family_member_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid family member ID")

        if request.horoscope_type not in ("general", "focused", "regeneration"):
            raise HTTPException(status_code=400, detail="Type must be: general, focused, regeneration")
        horoscope_type = request.horoscope_type
        focus_interest_id = request.focus_interest_id

    try:
        horoscope = await create_horoscope(
            user=current_user,
            db=db,
            target_date=target_date,
            family_member_id=family_member_id,
            horoscope_type=horoscope_type,
            focus_interest_id=focus_interest_id,
        )
        return HoroscopeResponse.model_validate(horoscope)
    except ValueError as e:
        error_msg = str(e)
        if "limit" in error_msg.lower():
            raise HTTPException(status_code=429, detail=error_msg)
        if "ad" in error_msg.lower() or "watch" in error_msg.lower():
            raise HTTPException(status_code=402, detail=error_msg)
        if "available for" in error_msg.lower():
            raise HTTPException(status_code=403, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)


@router.get("/today", response_model=HoroscopeResponse | None)
async def get_today(
    family_member_id: str | None = None,
    horoscope_type: str = "general",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get today's horoscope if already generated."""
    fm_id = UUID(family_member_id) if family_member_id else None
    horoscope = await get_todays_horoscope(
        current_user, db, family_member_id=fm_id, horoscope_type=horoscope_type
    )
    if horoscope is None:
        return None
    return HoroscopeResponse.model_validate(horoscope)


@router.get("/history", response_model=HoroscopeHistoryResponse)
async def get_history(
    family_member_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get last N horoscopes (depth depends on tier)."""
    tier = get_tier_config(current_user.subscription_tier)
    fm_id = UUID(family_member_id) if family_member_id else None
    history = await get_user_history(
        current_user.id, db, limit=tier.history_in_prompt, family_member_id=fm_id
    )
    return HoroscopeHistoryResponse(
        horoscopes=[HoroscopeResponse.model_validate(h) for h in history],
        total=len(history),
    )


@router.post("/{horoscope_id}/feedback", response_model=HoroscopeResponse)
async def feedback(
    horoscope_id: UUID,
    request: HoroscopeFeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit feedback (like/dislike) for a horoscope."""
    try:
        horoscope = await submit_feedback(
            horoscope_id=horoscope_id,
            user_id=current_user.id,
            feedback=request.feedback,
            db=db,
        )
        return HoroscopeResponse.model_validate(horoscope)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/limits")
async def get_my_limits(
    current_user: User = Depends(get_current_user),
):
    """Get current user's daily limits and remaining quota.

    Useful for frontend to show remaining horoscopes.
    """
    tier = get_tier_config(current_user.subscription_tier)
    return {
        "tier": tier.tier_id,
        "display_name": tier.display_name,
        "daily_general_limit": tier.daily_general_limit or "unlimited",
        "daily_focus_limit": tier.daily_focus_limit,
        "regeneration_limit": tier.regeneration_limit,
        "ads_required": tier.ads_required,
        "focus_sphere_enabled": tier.focus_sphere_enabled,
        "family_members_limit": tier.family_members_limit,
        "history_depth": tier.history_in_prompt,
    }
