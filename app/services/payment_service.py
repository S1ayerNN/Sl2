"""Payment service abstraction.

Provides a pluggable payment provider interface. The default StubPaymentProvider
instantly "confirms" payments for development/testing. Replace with a real
provider (YooKassa, Stripe, Tinkoff, etc.) when ready for production.

Architecture:
    PaymentProvider (ABC)
        |
        +-- StubPaymentProvider     <-- current (auto-confirms)
        +-- YooKassaPaymentProvider <-- future
        +-- StripePaymentProvider   <-- future

Usage:
    from app.services.payment_service import payment_provider, activate_subscription

    # Start payment
    result = await payment_provider.create_payment(user_id, tier_id, period, price)

    # On webhook / stub confirmation
    await activate_subscription(user, tier_id, period, db)
"""

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.services.tier_config import get_tier_config, TIER_CONFIGS

logger = logging.getLogger(__name__)


# --- Price calculation ---

def get_price(tier_id: str, period: str) -> int:
    """Get price in RUB for a tier + period combination.

    Returns 0 for free tier. Raises ValueError for invalid inputs.
    """
    if tier_id not in TIER_CONFIGS:
        raise ValueError(f"Unknown tier: {tier_id}")
    if tier_id == "free":
        raise ValueError("Cannot purchase free tier")
    if period not in ("month", "year"):
        raise ValueError(f"Invalid period: {period}. Use 'month' or 'year'.")

    tier = get_tier_config(tier_id)
    if period == "month":
        return tier.price_monthly_rub
    return tier.price_yearly_rub


def get_subscription_duration(period: str) -> timedelta:
    """Get subscription duration for a billing period."""
    if period == "month":
        return timedelta(days=30)
    if period == "year":
        return timedelta(days=365)
    raise ValueError(f"Invalid period: {period}")


# --- Payment Provider Interface ---

class PaymentProvider(ABC):
    """Abstract payment provider interface.

    Implement this for each payment gateway (YooKassa, Stripe, etc.).
    """

    @abstractmethod
    async def create_payment(
        self,
        user_id: str,
        tier_id: str,
        period: str,
        price_rub: int,
    ) -> dict:
        """Create a payment and return payment details.

        Returns:
            {
                "payment_id": str,
                "payment_url": str | None,  # redirect URL for hosted checkout
                "status": str,              # "pending" or "confirmed" (stub)
            }
        """
        ...

    @abstractmethod
    async def verify_webhook(self, payload: dict) -> dict:
        """Verify and parse incoming webhook from payment provider.

        Returns:
            {
                "payment_id": str,
                "status": "succeeded" | "failed",
                "user_id": str,
                "tier_id": str,
                "period": str,
            }
        """
        ...

    @abstractmethod
    async def cancel_subscription(self, user_id: str) -> bool:
        """Cancel recurring payments for a user. Returns True on success."""
        ...


class StubPaymentProvider(PaymentProvider):
    """Stub payment provider for development and testing.

    Instantly confirms all payments without actual charging.
    Stores pending payments in memory (lost on restart -- that's fine for a stub).
    """

    def __init__(self):
        # In-memory storage: payment_id -> payment details
        self._payments: dict[str, dict] = {}

    async def create_payment(
        self,
        user_id: str,
        tier_id: str,
        period: str,
        price_rub: int,
    ) -> dict:
        payment_id = f"stub_{uuid.uuid4().hex[:12]}"

        self._payments[payment_id] = {
            "payment_id": payment_id,
            "user_id": user_id,
            "tier_id": tier_id,
            "period": period,
            "price_rub": price_rub,
            "status": "confirmed",  # Stub: auto-confirm
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "STUB PAYMENT: user=%s tier=%s period=%s price=%d payment_id=%s (auto-confirmed)",
            user_id, tier_id, period, price_rub, payment_id,
        )

        return {
            "payment_id": payment_id,
            "payment_url": None,  # No redirect needed for stub
            "status": "confirmed",
        }

    async def verify_webhook(self, payload: dict) -> dict:
        """Stub webhook verification -- always succeeds if payment_id is known."""
        payment_id = payload.get("payment_id", "")
        payment = self._payments.get(payment_id)

        if not payment:
            raise ValueError(f"Unknown payment_id: {payment_id}")

        return {
            "payment_id": payment_id,
            "status": "succeeded",
            "user_id": payment["user_id"],
            "tier_id": payment["tier_id"],
            "period": payment["period"],
        }

    async def cancel_subscription(self, user_id: str) -> bool:
        """Stub cancellation -- always succeeds."""
        logger.info("STUB CANCEL: user=%s (auto-confirmed)", user_id)
        return True


# --- Subscription activation logic ---

async def activate_subscription(
    user: User,
    tier_id: str,
    period: str,
    db: AsyncSession,
) -> User:
    """Activate or extend a subscription for a user.

    If the user already has an active subscription that hasn't expired,
    the new period is added to the existing expiration date.
    Otherwise, the subscription starts from now.
    """
    duration = get_subscription_duration(period)
    now = datetime.now(timezone.utc)

    # Extend if currently active, otherwise start from now
    if user.subscription_expires and user.subscription_expires > now:
        new_expires = user.subscription_expires + duration
    else:
        new_expires = now + duration

    user.subscription_tier = tier_id
    user.subscription_expires = new_expires

    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(
        "Subscription activated: user=%s tier=%s expires=%s",
        user.id, tier_id, new_expires.isoformat(),
    )

    return user


async def deactivate_subscription(
    user: User,
    db: AsyncSession,
) -> User:
    """Cancel a subscription. User keeps access until expiration date.

    The tier is NOT immediately downgraded -- the user retains their
    current tier until subscription_expires passes. After that,
    is_premium returns False and they fall back to free behavior.
    """
    # Don't clear subscription_tier or subscription_expires
    # The user keeps access until expiry. The is_premium property
    # handles the expiry check automatically.
    logger.info(
        "Subscription cancelled: user=%s tier=%s expires=%s (access retained until expiry)",
        user.id, user.subscription_tier,
        user.subscription_expires.isoformat() if user.subscription_expires else "none",
    )

    return user


# --- Singleton provider instance ---
# Switch this to a real provider in production:
#   payment_provider = YooKassaPaymentProvider(api_key=settings.YOOKASSA_KEY)

payment_provider = StubPaymentProvider()
