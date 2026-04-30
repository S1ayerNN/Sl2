"""Subscription tier configuration.

All tier parameters are defined here in one place.
To change any limit, model, or feature flag - edit this file or override via env vars.

Tier hierarchy: free < plus < premium
Future: tarot readings as separate paid products (not subscription-tied)
"""

from dataclasses import dataclass, field
from app.core.config import settings


@dataclass
class TierConfig:
    """Configuration for a subscription tier."""
    # Identity
    tier_id: str
    display_name: str
    price_monthly_rub: int
    price_yearly_rub: int

    # AI model (OpenRouter format)
    ai_model: str
    # Prompt style
    prompt_style: str  # "basic", "extended", "detailed"
    prompt_max_words: int  # Target horoscope length

    # History context (how many past horoscopes included in prompt)
    history_in_prompt: int

    # Limits
    daily_general_limit: int  # General daily horoscopes (0 = unlimited)
    daily_focus_limit: int    # Focused (interest-specific) horoscopes
    regeneration_limit: int   # Re-generation attempts per day

    # Features
    ads_required: bool
    focus_sphere_enabled: bool
    family_members_limit: int

    # Future features
    tarot_enabled: bool = False
    compatibility_enabled: bool = False


# --- Tier Definitions ---
# All values can be overridden by env vars if needed

FREE_TIER = TierConfig(
    tier_id="free",
    display_name="Free",
    price_monthly_rub=0,
    price_yearly_rub=0,
    ai_model=settings.AI_MODEL_FREE,  # Default: google/gemini-flash-1.5
    prompt_style="basic",
    prompt_max_words=100,
    history_in_prompt=2,
    daily_general_limit=0,   # UNLIMITED (ad-supported)
    daily_focus_limit=0,     # No focus sphere access
    regeneration_limit=0,    # No regeneration
    ads_required=True,
    focus_sphere_enabled=False,
    family_members_limit=settings.FAMILY_MEMBERS_LIMIT_FREE,
)

PLUS_TIER = TierConfig(
    tier_id="plus",
    display_name="Plus",
    price_monthly_rub=149,
    price_yearly_rub=999,
    ai_model=settings.AI_MODEL_FREE,  # Same model, better prompt
    prompt_style="extended",
    prompt_max_words=200,
    history_in_prompt=3,
    daily_general_limit=3,   # 3 general horoscopes (self + 1 family)
    daily_focus_limit=1,     # 1 focused per day
    regeneration_limit=1,    # 1 retry per day
    ads_required=False,
    focus_sphere_enabled=True,
    family_members_limit=1,
)

PREMIUM_TIER = TierConfig(
    tier_id="premium",
    display_name="Premium",
    price_monthly_rub=299,
    price_yearly_rub=1999,
    ai_model=settings.AI_MODEL_PREMIUM,  # Better model
    prompt_style="detailed",
    prompt_max_words=250,
    history_in_prompt=5,
    daily_general_limit=6,   # 6 total (self + up to 5 family)
    daily_focus_limit=2,     # 2 focused per day
    regeneration_limit=3,    # 1 per person (self + family)
    ads_required=False,
    focus_sphere_enabled=True,
    family_members_limit=settings.FAMILY_MEMBERS_LIMIT_PREMIUM,
    compatibility_enabled=True,  # Post-MVP
)


# Registry
TIER_CONFIGS = {
    "free": FREE_TIER,
    "plus": PLUS_TIER,
    "premium": PREMIUM_TIER,
}


def get_tier_config(tier_id: str) -> TierConfig:
    """Get configuration for a subscription tier."""
    return TIER_CONFIGS.get(tier_id, FREE_TIER)


def get_all_tiers_for_api() -> list[dict]:
    """Get tier comparison data for frontend display."""
    return [
        {
            "tier_id": t.tier_id,
            "display_name": t.display_name,
            "price_monthly_rub": t.price_monthly_rub,
            "price_yearly_rub": t.price_yearly_rub,
            "features": {
                "ads_free": not t.ads_required,
                "daily_general_limit": t.daily_general_limit or "unlimited",
                "daily_focus_limit": t.daily_focus_limit,
                "regeneration_limit": t.regeneration_limit,
                "focus_sphere": t.focus_sphere_enabled,
                "family_members": t.family_members_limit,
                "history_depth": t.history_in_prompt,
                "horoscope_length": f"~{t.prompt_max_words} words",
                "compatibility": t.compatibility_enabled,
                "tarot": t.tarot_enabled,
            },
        }
        for t in [FREE_TIER, PLUS_TIER, PREMIUM_TIER]
    ]
