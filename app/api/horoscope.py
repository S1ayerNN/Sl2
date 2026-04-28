"""Horoscope API endpoints.

Users have NO text input for AI prompts. They can only:
- Request generation (optionally for a family member)
- View history
- Submit feedback (like/dislike)
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

router = APIRouter(prefix="/horoscope", tags=["Horoscope"])


@router.post("/generate", response_model=HoroscopeResponse)
async def generate_daily_horoscope(
    request: HoroscopeGenerateRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a personalized daily horoscope.

    Free users: must watch ad first (POST /ads/request-token + /ads/confirm).
    Premium users: generate directly, up to 20 per day.

    User has NO text input - horoscope is generated from profile data and history.
    Optionally specify family_member_id to generate for a family member.
    """
    target_date = None
    family_member_id = None

    if request:
        if request.target_date:
            try:
                target_date = date.fromisoformat(request.target_date)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid date format. Use YYYY-MM-DD",
                )
        if request.family_member_id:
            try:
                family_member_id = UUID(request.family_member_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid family member ID",
                )

    try:
        horoscope = await create_horoscope(
            user=current_user,
            db=db,
            target_date=target_date,
            family_member_id=family_member_id,
        )
        return HoroscopeResponse.model_validate(horoscope)
    except ValueError as e:
        error_msg = str(e)
        if "limit" in error_msg.lower():
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=error_msg)
        if "ad" in error_msg.lower():
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=error_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)


@router.get("/today", response_model=HoroscopeResponse | None)
async def get_today_horoscope(
    family_member_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get today's horoscope if already generated."""
    fm_id = UUID(family_member_id) if family_member_id else None
    horoscope = await get_todays_horoscope(current_user, db, family_member_id=fm_id)
    if horoscope is None:
        return None
    return HoroscopeResponse.model_validate(horoscope)


@router.get("/history", response_model=HoroscopeHistoryResponse)
async def get_horoscope_history(
    family_member_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the last 5 horoscopes with feedback."""
    fm_id = UUID(family_member_id) if family_member_id else None
    history = await get_user_history(current_user.id, db, family_member_id=fm_id)
    return HoroscopeHistoryResponse(
        horoscopes=[HoroscopeResponse.model_validate(h) for h in history],
        total=len(history),
    )


@router.post("/{horoscope_id}/feedback", response_model=HoroscopeResponse)
async def submit_horoscope_feedback(
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
