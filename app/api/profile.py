"""Profile API endpoints.

PII is encrypted in DB and decrypted only when returning to the authenticated user.
Interests are selected from a predefined list only - no free text input.
"""

import os
import re
import uuid as uuid_mod
from datetime import date, time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.core.config import settings
from app.core.crypto import decrypt_pii, encrypt_pii, hash_identifier
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import (
    User, FamilyMember, Gender, FamilyRelation,
)
from app.schemas.user import (
    AVAILABLE_GENDERS, AVAILABLE_RELATIONS,
    AvailableOptionsResponse, FamilyMemberCreate, FamilyMemberResponse,
    ProfileCompletenessHint, UserProfile, UserProfileUpdate,
)
from app.services.interest_catalog import (
    get_catalog_for_api,
    validate_interest_ids,
)
from app.services.tier_config import get_all_tiers_for_api, get_tier_config
from app.services.zodiac_service import get_zodiac_sign

router = APIRouter(prefix="/profile", tags=["Profile"])


def _user_to_profile(user: User) -> UserProfile:
    """Convert User model to profile response, decrypting PII."""
    return UserProfile(
        id=user.id,
        name=decrypt_pii(user.name_encrypted),
        birth_date=user.birth_date,
        gender=user.gender,
        zodiac_sign=user.zodiac_sign,
        birth_time=user.birth_time,
        birth_place=decrypt_pii(user.birth_place_encrypted) if user.birth_place_encrypted else None,
        email=decrypt_pii(user.email_encrypted) if user.email_encrypted else None,
        profession=decrypt_pii(user.profession_encrypted) if user.profession_encrypted else None,
        avatar_url=user.avatar_url,
        interests=user.interests or [],
        subscription_tier=user.subscription_tier,
        subscription_expires=user.subscription_expires,
        is_premium=user.is_premium,
        family_members_count=len(user.family_members) if user.family_members else 0,
        family_members_limit=get_tier_config(user.subscription_tier).family_members_limit,
        profile_completeness=user.profile_completeness,
        created_at=user.created_at,
    )


@router.get("/options", response_model=AvailableOptionsResponse)
async def get_available_options():
    """Get predefined options for interests, genders, and family relations.

    Frontend MUST use these values - no free text input for these fields.
    """
    return AvailableOptionsResponse(
        interests=get_catalog_for_api(),
        genders=AVAILABLE_GENDERS,
        relations=AVAILABLE_RELATIONS,
    )


@router.get("/me", response_model=UserProfile)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
):
    """Get current user's profile (PII decrypted)."""
    return _user_to_profile(current_user)


@router.patch("/me", response_model=UserProfile)
async def update_my_profile(
    update_data: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user's profile.

    - Name, birth_place, email are encrypted before storage
    - Interests MUST be from the predefined list
    """
    if update_data.name is not None:
        name = update_data.name.strip()
        if len(name) < 2 or len(name) > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Name must be between 2 and 100 characters",
            )
        current_user.name_encrypted = encrypt_pii(name)

    if update_data.birth_time is not None:
        if not re.match(r'^\d{1,2}:\d{2}$', update_data.birth_time):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid time format. Use HH:MM",
            )
        h, m = map(int, update_data.birth_time.split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid time. Hours 0-23, minutes 0-59",
            )
        current_user.birth_time = time(h, m)

    if update_data.birth_place is not None:
        place = update_data.birth_place.strip()
        if len(place) > 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Birth place must be under 200 characters",
            )
        current_user.birth_place_encrypted = encrypt_pii(place)

    if update_data.email is not None:
        email = update_data.email.strip().lower()
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email format",
            )
        current_user.email_encrypted = encrypt_pii(email)
        current_user.email_hash = hash_identifier(email)

    if update_data.profession is not None:
        prof = update_data.profession.strip()
        if len(prof) > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Profession must be under 100 characters",
            )
        current_user.profession_encrypted = encrypt_pii(prof) if prof else None

    if update_data.interests is not None:
        # Validate: ONLY active catalog interests allowed
        current_user.interests = validate_interest_ids(update_data.interests)

    current_user.profile_completeness = current_user.calculate_completeness()
    await db.flush()

    return _user_to_profile(current_user)


@router.get("/completeness", response_model=ProfileCompletenessHint)
async def get_profile_completeness(
    current_user: User = Depends(get_current_user),
):
    """Get profile completeness and hints for missing fields."""
    missing = []
    hints = {
        "birth_time": "Укажи время рождения для расчета асцендента",
        "birth_place_encrypted": "Добавь место рождения для натальной карты",
        "email_encrypted": "Добавь email для восстановления аккаунта",
        "interests": "Выбери интересующие сферы жизни для персонализации",
    }

    if current_user.birth_time is None:
        missing.append("birth_time")
    if not current_user.birth_place_encrypted:
        missing.append("birth_place")
    if not current_user.email_encrypted:
        missing.append("email")
    if not current_user.interests:
        missing.append("interests")

    if missing:
        field_key = {
            "birth_time": "birth_time",
            "birth_place": "birth_place_encrypted",
            "email": "email_encrypted",
            "interests": "interests",
        }.get(missing[0], missing[0])
        hint_message = hints.get(field_key, "Заполни профиль для лучших гороскопов")
    else:
        hint_message = "Профиль полностью заполнен! Гороскопы максимально персонализированы."

    return ProfileCompletenessHint(
        completeness=current_user.profile_completeness,
        missing_fields=missing,
        hint_message=hint_message,
    )


# --- Family Members ---


@router.get("/family", response_model=list[FamilyMemberResponse])
async def list_family_members(
    current_user: User = Depends(get_current_user),
):
    """List all family member profiles."""
    members = current_user.family_members or []
    return [
        FamilyMemberResponse(
            id=m.id,
            name=decrypt_pii(m.name_encrypted),
            relation=m.relation,
            birth_date=m.birth_date,
            birth_time=m.birth_time,
            gender=m.gender,
            zodiac_sign=m.zodiac_sign,
            interests=m.interests or [],
            created_at=m.created_at,
        )
        for m in members
    ]


@router.post("/family", response_model=FamilyMemberResponse, status_code=201)
async def add_family_member(
    data: FamilyMemberCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a family member profile.

    Free users: 0 members allowed (only self)
    Premium users: up to 5 members
    """
    tier = get_tier_config(current_user.subscription_tier)
    limit = tier.family_members_limit
    current_count = len(current_user.family_members) if current_user.family_members else 0

    if current_count >= limit:
        if limit == 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Family members available only for paid subscribers",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {limit} family members allowed for your subscription tier",
        )

    # Validate enums
    if data.gender not in [g.value for g in Gender]:
        raise HTTPException(status_code=400, detail="Invalid gender")
    if data.relation not in [r.value for r in FamilyRelation]:
        raise HTTPException(status_code=400, detail="Invalid relation")

    name = data.name.strip()
    if len(name) < 2 or len(name) > 100:
        raise HTTPException(status_code=400, detail="Name must be 2-100 characters")

    birth_date = date.fromisoformat(data.birth_date)
    zodiac_sign = get_zodiac_sign(birth_date)

    birth_time_val = None
    if data.birth_time:
        h, m = map(int, data.birth_time.split(":"))
        birth_time_val = time(h, m)

    interests = []
    if data.interests:
        interests = validate_interest_ids(data.interests)

    member = FamilyMember(
        owner_id=current_user.id,
        name_encrypted=encrypt_pii(name),
        relation=data.relation,
        birth_date=birth_date,
        birth_time=birth_time_val,
        gender=data.gender,
        zodiac_sign=zodiac_sign,
        interests=interests,
    )
    db.add(member)
    await db.flush()

    return FamilyMemberResponse(
        id=member.id,
        name=name,
        relation=member.relation,
        birth_date=member.birth_date,
        birth_time=member.birth_time,
        gender=member.gender,
        zodiac_sign=member.zodiac_sign,
        interests=member.interests or [],
        created_at=member.created_at,
    )


@router.delete("/family/{member_id}", status_code=204)
async def delete_family_member(
    member_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a family member profile."""
    result = await db.execute(
        select(FamilyMember)
        .where(FamilyMember.id == member_id)
        .where(FamilyMember.owner_id == current_user.id)
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Family member not found")
    await db.delete(member)
    await db.flush()


# --- Avatar Upload ---

AVATAR_UPLOAD_DIR = Path("/app/uploads/avatars")
AVATAR_MAX_SIZE = 1 * 1024 * 1024  # 1 MB
AVATAR_ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
AVATAR_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload user avatar image.

    Validates:
    - File extension (jpg, png, webp, gif)
    - MIME type (image/jpeg, image/png, image/webp, image/gif)
    - File size (max 1 MB)
    """
    # Validate MIME type
    if file.content_type not in AVATAR_ALLOWED_MIMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: {file.content_type}. Allowed: JPEG, PNG, WebP, GIF",
        )

    # Validate extension
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in AVATAR_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file extension: {ext}. Allowed: {', '.join(AVATAR_ALLOWED_EXTENSIONS)}",
        )

    # Read and validate size
    contents = await file.read()
    if len(contents) > AVATAR_MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large: {len(contents)} bytes. Maximum: {AVATAR_MAX_SIZE} bytes (1 MB)",
        )

    if len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file",
        )

    # Compress and resize avatar (max 300x300, JPEG quality 85)
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(contents))
        # Convert to RGB if needed (e.g. PNG with alpha)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        # Resize if larger than 300x300
        max_size = (300, 300)
        if img.width > max_size[0] or img.height > max_size[1]:
            img.thumbnail(max_size, Image.LANCZOS)
        # Save as optimized JPEG
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=85, optimize=True)
        contents = buf.getvalue()
        ext = '.jpg'
    except ImportError:
        pass  # Pillow not installed, save original
    except Exception:
        pass  # If image processing fails, save original

    # Save file
    AVATAR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{current_user.id}{ext}"
    filepath = AVATAR_UPLOAD_DIR / filename
    with open(filepath, "wb") as f:
        f.write(contents)

    # Update user avatar URL
    avatar_url = f"/uploads/avatars/{filename}"
    current_user.avatar_url = avatar_url
    await db.flush()

    return {"avatar_url": avatar_url}


# --- Subscription Tiers ---


@router.get("/tiers")
async def get_subscription_tiers():
    """Get all subscription tiers with features and pricing.

    Use this to display the subscription comparison page.
    """
    return get_all_tiers_for_api()
