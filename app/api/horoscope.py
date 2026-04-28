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

    Free users: uses GPT-4o-mini, limited to 3 per day.
    Premium users: uses GPT-4o, up to 20 per day.

    The horoscope is personalized based on:
    - User's zodiac sign and profile data
    - Last 5 horoscopes and their feedback (like/dislike)
    """
    target_date = None
    if request and request.target_date:
        try:
            target_date = date.fromisoformat(request.target_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Use YYYY-MM-DD",
            )

    try:
        horoscope = await create_horoscope(
            user=current_user,
            db=db,
            target_date=target_date,
        )
        return HoroscopeResponse.model_validate(horoscope)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
        )


@router.get("/today", response_model=HoroscopeResponse | None)
async def get_today_horoscope(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get today's horoscope if it was already generated.

    Returns null if no horoscope has been generated today.
    Use POST /generate to create one.
    """
    horoscope = await get_todays_horoscope(current_user, db)
    if horoscope is None:
        return None
    return HoroscopeResponse.model_validate(horoscope)


@router.get("/history", response_model=HoroscopeHistoryResponse)
async def get_horoscope_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the last 5 horoscopes with feedback.

    This is the same data used by AI to personalize future horoscopes.
    """
    history = await get_user_history(current_user.id, db)
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
    """Submit feedback (like/dislike) for a horoscope.

    This feedback is stored and used by AI to improve future horoscopes.
    """
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
