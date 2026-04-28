"""Subscription management API endpoints.

Handles subscription purchase, status, cancellation, and payment webhooks.
Currently uses StubPaymentProvider (auto-confirms payments).
Replace with real provider (YooKassa, Stripe, etc.) for production.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.subscription import (
    CancelSubscriptionResponse,
    PaymentWebhookPayload,
    SubscribeRequest,
    SubscribeResponse,
    SubscriptionStatusResponse,
)
from app.services.payment_service import (
    activate_subscription,
    deactivate_subscription,
    get_price,
    payment_provider,
)
from app.services.tier_config import get_tier_config, TIER_CONFIGS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscription", tags=["Subscription"])


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(
    request: SubscribeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a subscription purchase.

    In stub mode: instantly activates the subscription (no real payment).
    In production: returns a payment_url for redirect to payment gateway.

    **Request:**
    - tier_id: "plus" or "premium"
    - period: "month" or "year"

    **Validation:**
    - Cannot subscribe to "free" (it's the default)
    - Cannot subscribe to the same tier you already have (if active)
    """
    tier_id = request.tier_id
    period = request.period

    # Validate tier
    if tier_id not in TIER_CONFIGS or tier_id == "free":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tier: {tier_id}. Choose 'plus' or 'premium'.",
        )

    # Validate period
    if period not in ("month", "year"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid period. Choose 'month' or 'year'.",
        )

    # Check if already on this tier and active
    if (
        current_user.subscription_tier == tier_id
        and current_user.subscription_expires
        and current_user.subscription_expires > datetime.now(timezone.utc)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You already have an active {tier_id} subscription until "
                   f"{current_user.subscription_expires.strftime('%d.%m.%Y')}. "
                   "It will be extended on renewal.",
        )

    # Calculate price
    try:
        price = get_price(tier_id, period)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Create payment via provider
    payment_result = await payment_provider.create_payment(
        user_id=str(current_user.id),
        tier_id=tier_id,
        period=period,
        price_rub=price,
    )

    # Stub mode: payment is auto-confirmed, activate immediately
    if payment_result["status"] == "confirmed":
        await activate_subscription(current_user, tier_id, period, db)

        tier_config = get_tier_config(tier_id)
        return SubscribeResponse(
            status="activated",
            payment_id=payment_result["payment_id"],
            payment_url=None,
            tier_id=tier_id,
            period=period,
            price_rub=price,
            message=f"Подписка {tier_config.display_name} активирована! "
                    f"(Stub-режим: оплата не списана)",
        )

    # Production mode: return payment URL for redirect
    return SubscribeResponse(
        status="pending_payment",
        payment_id=payment_result["payment_id"],
        payment_url=payment_result.get("payment_url"),
        tier_id=tier_id,
        period=period,
        price_rub=price,
        message="Перейдите по ссылке для оплаты",
    )


@router.get("/status", response_model=SubscriptionStatusResponse)
async def get_subscription_status(
    current_user: User = Depends(get_current_user),
):
    """Get current subscription status.

    Returns tier info, expiration date, and whether the subscription is active.
    """
    tier = get_tier_config(current_user.subscription_tier)
    now = datetime.now(timezone.utc)

    is_active = (
        current_user.subscription_tier != "free"
        and current_user.subscription_expires is not None
        and current_user.subscription_expires > now
    )

    return SubscriptionStatusResponse(
        tier_id=current_user.subscription_tier,
        display_name=tier.display_name,
        is_active=is_active,
        expires_at=current_user.subscription_expires,
        auto_renew=False,  # Stub: no auto-renewal yet
        can_cancel=is_active,
    )


@router.post("/cancel", response_model=CancelSubscriptionResponse)
async def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel current subscription.

    The user retains access until the subscription expiration date.
    After expiry, they automatically fall back to the free tier.
    In production, this would also cancel recurring payments with the provider.
    """
    if current_user.subscription_tier == "free":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active subscription to cancel.",
        )

    now = datetime.now(timezone.utc)
    if (
        current_user.subscription_expires is None
        or current_user.subscription_expires <= now
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription has already expired.",
        )

    # Cancel with payment provider (stop recurring charges)
    await payment_provider.cancel_subscription(str(current_user.id))

    # Mark as cancelled (user keeps access until expiry)
    await deactivate_subscription(current_user, db)

    return CancelSubscriptionResponse(
        status="cancelled",
        message=f"Подписка отменена. Доступ сохранится до "
                f"{current_user.subscription_expires.strftime('%d.%m.%Y')}.",
        tier_id=current_user.subscription_tier,
        expires_at=current_user.subscription_expires,
    )


@router.post("/webhook")
async def payment_webhook(
    payload: PaymentWebhookPayload,
    db: AsyncSession = Depends(get_db),
):
    """Payment provider webhook endpoint.

    Called by the payment provider when payment status changes.
    In production, this should verify the webhook signature.

    **Security notes for production:**
    - Verify webhook signature (HMAC, IP whitelist, etc.)
    - Use idempotency keys to prevent double-processing
    - Log all webhook events for audit trail
    """
    try:
        verified = await payment_provider.verify_webhook(payload.model_dump())
    except ValueError as e:
        logger.warning("Webhook verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if verified["status"] != "succeeded":
        logger.info("Payment failed: %s", verified["payment_id"])
        return {"status": "noted", "message": "Payment was not successful."}

    # Find user and activate subscription
    from sqlalchemy import select
    user_id = verified["user_id"]
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        logger.error("Webhook: user not found: %s", user_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await activate_subscription(
        user,
        verified["tier_id"],
        verified["period"],
        db,
    )

    logger.info(
        "Webhook: subscription activated via webhook for user=%s tier=%s",
        user_id, verified["tier_id"],
    )

    return {"status": "ok", "message": "Subscription activated."}
