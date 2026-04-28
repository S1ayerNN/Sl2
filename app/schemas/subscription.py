"""Subscription payment schemas.

Request/response models for the subscription payment flow.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SubscribeRequest(BaseModel):
    """Запрос на оформление подписки."""
    tier_id: str          # "plus" или "premium"
    period: str = "month"  # "month" или "year"


class SubscribeResponse(BaseModel):
    """Ответ с URL оплаты или подтверждением."""
    status: str               # "pending_payment" или "activated" (stub)
    payment_url: Optional[str] = None
    order_id: str             # Внутренний ID заказа
    tier_id: str
    period: str
    price_rub: int
    message: str


class PaymentWebhookPayload(BaseModel):
    """Входящий вебхук от платежного провайдера.

    В продакшене формат зависит от провайдера (YooKassa, Stripe и т.д.).
    Stub-версия использует упрощенный формат.
    """
    payment_provider_id: str  # ID платежа у провайдера
    status: str               # "succeeded" или "failed"


class SubscriptionStatusResponse(BaseModel):
    """Текущий статус подписки."""
    tier_id: str
    display_name: str
    is_active: bool
    expires_at: Optional[datetime] = None
    auto_renew: bool = False
    can_cancel: bool = False


class CancelSubscriptionResponse(BaseModel):
    """Ответ после отмены подписки."""
    status: str
    message: str
    tier_id: str
    expires_at: Optional[datetime] = None
