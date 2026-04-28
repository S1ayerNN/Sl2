"""Subscription payment schemas.

Request/response models for the subscription payment flow.
Payment provider integration is stubbed -- replace StubPaymentProvider
with a real provider (YooKassa, Stripe, etc.) when ready.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class SubscribeRequest(BaseModel):
    """Request to start a subscription."""
    tier_id: str          # "plus" or "premium"
    period: str = "month"  # "month" or "year"


class SubscribeResponse(BaseModel):
    """Response with payment URL or confirmation."""
    status: str               # "pending_payment" or "activated" (stub mode)
    payment_url: Optional[str] = None  # Redirect URL for real providers
    payment_id: Optional[str] = None   # Internal payment tracking ID
    tier_id: str
    period: str
    price_rub: int
    message: str


class PaymentWebhookPayload(BaseModel):
    """Incoming webhook from payment provider.

    In production, this would be provider-specific (YooKassa, Stripe, etc.).
    The stub version uses a simplified format.
    """
    payment_id: str
    status: str          # "succeeded" or "failed"
    provider: str = "stub"


class SubscriptionStatusResponse(BaseModel):
    """Current subscription status."""
    tier_id: str
    display_name: str
    is_active: bool
    expires_at: Optional[datetime] = None
    auto_renew: bool = False
    can_cancel: bool = False


class CancelSubscriptionResponse(BaseModel):
    """Response after cancellation."""
    status: str
    message: str
    tier_id: str
    expires_at: Optional[datetime] = None
