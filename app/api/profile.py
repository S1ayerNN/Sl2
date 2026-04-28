from datetime import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.user import ProfileCompletenessHint, UserProfile, UserProfileUpdate

router = APIRouter(prefix="/profile", tags=["Profile"])


@router.get("/me", response_model=UserProfile)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
):
    """Get current user's profile."""
    return UserProfile(
        id=current_user.id,
        name=current_user.name,
        birth_date=current_user.birth_date,
        gender=current_user.gender,
        zodiac_sign=current_user.zodiac_sign,
        birth_time=current_user.birth_time,
        birth_place=current_user.birth_place,
        email=current_user.email,
        avatar_url=current_user.avatar_url,
        interests=current_user.interests,
        subscription_tier=current_user.subscription_tier,
        subscription_expires=current_user.subscription_expires,
        is_premium=current_user.is_premium,
        profile_completeness=current_user.profile_completeness,
        created_at=current_user.created_at,
    )


@router.patch("/me", response_model=UserProfile)
async def update_my_profile(
    update_data: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user's profile.

    Only provided fields will be updated. Use this for progressive profile completion.
    """
    if update_data.name is not None:
        current_user.name = update_data.name

    if update_data.birth_time is not None:
        try:
            hours, minutes = update_data.birth_time.split(":")
            current_user.birth_time = time(int(hours), int(minutes))
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid time format. Use HH:MM",
            )

    if update_data.birth_place is not None:
        current_user.birth_place = update_data.birth_place

    if update_data.email is not None:
        current_user.email = update_data.email

    if update_data.interests is not None:
        current_user.interests = update_data.interests

    # Recalculate profile completeness
    current_user.profile_completeness = current_user.calculate_completeness()

    await db.flush()

    return UserProfile(
        id=current_user.id,
        name=current_user.name,
        birth_date=current_user.birth_date,
        gender=current_user.gender,
        zodiac_sign=current_user.zodiac_sign,
        birth_time=current_user.birth_time,
        birth_place=current_user.birth_place,
        email=current_user.email,
        avatar_url=current_user.avatar_url,
        interests=current_user.interests,
        subscription_tier=current_user.subscription_tier,
        subscription_expires=current_user.subscription_expires,
        is_premium=current_user.is_premium,
        profile_completeness=current_user.profile_completeness,
        created_at=current_user.created_at,
    )


@router.get("/completeness", response_model=ProfileCompletenessHint)
async def get_profile_completeness(
    current_user: User = Depends(get_current_user),
):
    """Get profile completeness status and hints about missing fields.

    Use this to prompt users to fill in additional data for better horoscopes.
    """
    missing = []
    hints = {
        "birth_time": "Укажи время рождения для расчета асцендента",
        "birth_place": "Добавь место рождения для натальной карты",
        "email": "Добавь email для восстановления аккаунта",
        "interests": "Выбери интересующие сферы жизни для персонализации",
    }

    if current_user.birth_time is None:
        missing.append("birth_time")
    if current_user.birth_place is None:
        missing.append("birth_place")
    if current_user.email is None:
        missing.append("email")
    if not current_user.interests:
        missing.append("interests")

    if missing:
        first_missing = missing[0]
        hint_message = hints.get(first_missing, "Заполни профиль для лучших гороскопов")
    else:
        hint_message = "Твой профиль полностью заполнен! Гороскопы максимально персонализированы."

    return ProfileCompletenessHint(
        completeness=current_user.profile_completeness,
        missing_fields=missing,
        hint_message=hint_message,
    )
