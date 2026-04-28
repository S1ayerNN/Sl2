"""Debug/testing endpoints for prompt inspection and horoscope quality testing.

These endpoints are only available when DEBUG=true in .env.
They allow you to:
- Preview the exact prompt that would be sent to AI
- Test generation with mock profile data (without creating a real user)
- View current AI configuration (models, provider)
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.services.ai_service import build_full_prompt, client
from app.services.content_safety import check_content_safety
from app.services.interest_catalog import get_catalog_for_api

router = APIRouter(prefix="/debug", tags=["Debug (dev only)"])


class PromptPreviewRequest(BaseModel):
    """Mock profile data for prompt preview."""
    zodiac_sign: str = "Овен"
    gender: str = "male"
    name: str = "Тестовый Пользователь"
    target_date: Optional[str] = None
    birth_time: Optional[str] = None
    birth_place: Optional[str] = None
    interests: list[str] = ["love", "career"]


class PromptPreviewResponse(BaseModel):
    """Full prompt that would be sent to AI."""
    system_prompt: str
    user_prompt: str
    model_free: str
    model_premium: str
    ai_provider_url: str
    estimated_input_tokens: int  # Rough estimate


class TestGenerateRequest(BaseModel):
    """Request for test generation."""
    zodiac_sign: str = "Овен"
    gender: str = "female"
    name: str = "Анна"
    interests: list[str] = ["love", "health", "spirituality"]
    target_date: Optional[str] = None
    use_premium_model: bool = False


class TestGenerateResponse(BaseModel):
    """Test generation result with diagnostics."""
    horoscope_text: str
    model_used: str
    safety_passed: bool
    safety_violation: Optional[str] = None
    prompt_length_chars: int
    response_length_chars: int


def _require_debug():
    """Dependency that blocks access unless DEBUG=true."""
    if not settings.DEBUG:
        raise HTTPException(
            status_code=403,
            detail="Debug endpoints are only available when DEBUG=true",
        )


@router.get("/config", dependencies=[Depends(_require_debug)])
async def get_ai_config():
    """View current AI configuration."""
    return {
        "ai_provider_url": settings.AI_BASE_URL,
        "model_free": settings.AI_MODEL_FREE,
        "model_premium": settings.AI_MODEL_PREMIUM,
        "max_tokens": settings.AI_MAX_TOKENS,
        "temperature": settings.AI_TEMPERATURE,
        "interest_catalog": get_catalog_for_api(),
        "daily_limit_free": settings.HOROSCOPE_DAILY_LIMIT_FREE,
        "daily_limit_premium": settings.HOROSCOPE_DAILY_LIMIT_PREMIUM,
    }


@router.post("/prompt-preview", response_model=PromptPreviewResponse, dependencies=[Depends(_require_debug)])
async def preview_prompt(request: PromptPreviewRequest):
    """Preview the exact prompt that would be sent to AI.

    Use this to understand how user data maps to prompts
    and test different profile combinations.
    """
    target = date.fromisoformat(request.target_date) if request.target_date else date.today()

    system_prompt, user_prompt = build_full_prompt(
        zodiac_sign=request.zodiac_sign,
        gender=request.gender,
        name=request.name,
        target_date=target,
        birth_place=request.birth_place,
        interests=request.interests,
    )

    # Rough token estimate (1 token ~ 4 chars for Russian)
    total_chars = len(system_prompt) + len(user_prompt)
    estimated_tokens = total_chars // 3  # Russian is denser than English

    return PromptPreviewResponse(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_free=settings.AI_MODEL_FREE,
        model_premium=settings.AI_MODEL_PREMIUM,
        ai_provider_url=settings.AI_BASE_URL,
        estimated_input_tokens=estimated_tokens,
    )


@router.post("/test-generate", response_model=TestGenerateResponse, dependencies=[Depends(_require_debug)])
async def test_generate(request: TestGenerateRequest):
    """Generate a test horoscope with mock data.

    Use this to evaluate horoscope quality, test different models,
    and verify content safety without creating real users.
    Counts against no limits or ad requirements.
    """
    target = date.fromisoformat(request.target_date) if request.target_date else date.today()
    model = settings.AI_MODEL_PREMIUM if request.use_premium_model else settings.AI_MODEL_FREE

    system_prompt, user_prompt = build_full_prompt(
        zodiac_sign=request.zodiac_sign,
        gender=request.gender,
        name=request.name,
        target_date=target,
        interests=request.interests,
    )

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=settings.AI_MAX_TOKENS,
            temperature=settings.AI_TEMPERATURE,
        )
        horoscope_text = response.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI provider error: {type(e).__name__}")

    is_safe, violation = check_content_safety(horoscope_text)

    return TestGenerateResponse(
        horoscope_text=horoscope_text,
        model_used=model,
        safety_passed=is_safe,
        safety_violation=violation,
        prompt_length_chars=len(system_prompt) + len(user_prompt),
        response_length_chars=len(horoscope_text),
    )


@router.post("/safety-check", dependencies=[Depends(_require_debug)])
async def test_safety_check(text: str):
    """Test content safety filter on arbitrary text.

    Use this to verify the safety filter works correctly.
    """
    is_safe, violation = check_content_safety(text)
    return {
        "text_length": len(text),
        "is_safe": is_safe,
        "violation_category": violation,
    }
