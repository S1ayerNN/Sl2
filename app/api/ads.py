"""Ad verification API endpoints.

Flow for free users:
1. POST /ads/request-token -> get a one-time token
2. Client shows AdMob Rewarded Video
3. POST /ads/confirm -> confirm ad was watched (with token)
4. POST /horoscope/generate -> generate horoscope (verified server-side)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.horoscope import AdConfirmRequest, AdTokenResponse
from app.services.ad_service import confirm_ad_viewed, create_ad_token

router = APIRouter(prefix="/ads", tags=["Ads"])


@router.post("/request-token", response_model=AdTokenResponse)
async def request_ad_token(
    current_user: User = Depends(get_current_user),
):
    """Request a one-time ad viewing token.

    Premium users don't need this - they can generate horoscopes directly.
    """
    if current_user.is_premium:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Premium users don't need ad tokens",
        )

    token = await create_ad_token(str(current_user.id))
    return AdTokenResponse(
        token=token,
        expires_in_seconds=settings.AD_VIEW_TOKEN_TTL_SECONDS,
    )


@router.post("/confirm")
async def confirm_ad(
    request: AdConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm that an ad was watched.

    Call this after the client has finished showing the rewarded video.
    The token is one-time use and expires after 5 minutes.
    """
    success = await confirm_ad_viewed(
        user_id=str(current_user.id),
        token=request.token,
        db=db,
        user=current_user,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired ad token",
        )

    return {"status": "confirmed", "message": "Ad verified. You can now generate a horoscope."}
