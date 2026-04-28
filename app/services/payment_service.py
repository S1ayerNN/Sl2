"""Payment service -- безопасная обработка подписок.

Pluggable provider interface + реестр подписок (subscription_events).
StubPaymentProvider для разработки, заменяется на реальный провайдер.

Безопасность:
- Идемпотентность: повторная обработка одного payment_id не дублирует активацию
- Webhook auth: проверка секрета (заголовок X-Webhook-Secret)
- Хранимый реестр: все события в subscription_events (append-only)
- Нет PII / платежных данных в subscription_events
- Rate limiting на subscribe через Redis
- Защита от даунгрейда
"""

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.models.subscription import SubscriptionEvent, SubscriptionEventType
from app.services.tier_config import get_tier_config, TIER_CONFIGS

logger = logging.getLogger(__name__)

# Иерархия тарифов (для проверки даунгрейда)
TIER_HIERARCHY = {"free": 0, "plus": 1, "premium": 2}


# --- Цены ---

def get_price(tier_id: str, period: str) -> int:
    """Получить цену в рублях для тарифа + периода."""
    if tier_id not in TIER_CONFIGS:
        raise ValueError(f"Неизвестный тариф: {tier_id}")
    if tier_id == "free":
        raise ValueError("Нельзя купить бесплатный тариф")
    if period not in ("month", "year"):
        raise ValueError(f"Неверный период: {period}. Используйте 'month' или 'year'.")

    tier = get_tier_config(tier_id)
    if period == "month":
        return tier.price_monthly_rub
    return tier.price_yearly_rub


def get_subscription_duration(period: str) -> timedelta:
    """Длительность подписки для периода."""
    if period == "month":
        return timedelta(days=30)
    if period == "year":
        return timedelta(days=365)
    raise ValueError(f"Неверный период: {period}")


def is_downgrade(current_tier: str, new_tier: str) -> bool:
    """Проверить, является ли смена тарифа даунгрейдом."""
    return TIER_HIERARCHY.get(new_tier, 0) < TIER_HIERARCHY.get(current_tier, 0)


# --- Rate limiting ---

async def check_subscribe_rate_limit(user_id: str) -> bool:
    """Проверить rate limit на подписку (макс 5 попыток в час).

    Возвращает True если лимит не превышен.
    """
    from app.core.redis import redis_client
    key = f"subscribe_rate:{user_id}"
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, 3600)  # TTL 1 час
    return count <= 5


# --- Реестр подписок ---

async def create_order(
    user_id: uuid.UUID,
    tier_id: str,
    period: str,
    amount_rub: int,
    db: AsyncSession,
) -> SubscriptionEvent:
    """Создать заказ в реестре подписок."""
    order_id = f"order_{uuid.uuid4().hex[:16]}"

    event = SubscriptionEvent(
        user_id=user_id,
        event_type=SubscriptionEventType.ORDER_CREATED,
        tier_id=tier_id,
        period=period,
        amount_rub=amount_rub,
        order_id=order_id,
        status="pending",
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    logger.info(
        "Заказ создан: order_id=%s user=%s tier=%s period=%s amount=%d",
        order_id, user_id, tier_id, period, amount_rub,
    )
    return event


async def find_order_by_id(order_id: str, db: AsyncSession) -> SubscriptionEvent | None:
    """Найти заказ по order_id."""
    result = await db.execute(
        select(SubscriptionEvent)
        .where(SubscriptionEvent.order_id == order_id)
        .where(SubscriptionEvent.event_type == SubscriptionEventType.ORDER_CREATED)
    )
    return result.scalar_one_or_none()


async def find_order_by_provider_id(
    provider_id: str, db: AsyncSession
) -> SubscriptionEvent | None:
    """Найти заказ по payment_provider_id."""
    result = await db.execute(
        select(SubscriptionEvent)
        .where(SubscriptionEvent.payment_provider_id == provider_id)
        .where(SubscriptionEvent.event_type == SubscriptionEventType.ORDER_CREATED)
    )
    return result.scalar_one_or_none()


async def is_payment_already_processed(order_id: str, db: AsyncSession) -> bool:
    """Проверить, был ли платеж уже обработан (идемпотентность)."""
    result = await db.execute(
        select(SubscriptionEvent)
        .where(SubscriptionEvent.order_id == order_id)
        .where(SubscriptionEvent.event_type == SubscriptionEventType.ACTIVATED)
    )
    return result.scalar_one_or_none() is not None


async def log_event(
    user_id: uuid.UUID,
    event_type: str,
    order_id: str,
    tier_id: str,
    period: str,
    amount_rub: int,
    status: str,
    db: AsyncSession,
    payment_provider_id: str | None = None,
    meta: str | None = None,
) -> SubscriptionEvent:
    """Записать событие в реестр подписок."""
    event = SubscriptionEvent(
        user_id=user_id,
        event_type=event_type,
        tier_id=tier_id,
        period=period,
        amount_rub=amount_rub,
        order_id=order_id,
        payment_provider_id=payment_provider_id,
        status=status,
        meta=meta,
    )
    db.add(event)
    await db.commit()
    return event


# --- Payment Provider Interface ---

class PaymentProvider(ABC):
    """Абстрактный интерфейс платежного провайдера."""

    @abstractmethod
    async def create_payment(
        self,
        order_id: str,
        user_id: str,
        tier_id: str,
        period: str,
        price_rub: int,
    ) -> dict:
        """Создать платеж. Возвращает:
        {
            "payment_provider_id": str,
            "payment_url": str | None,
            "status": "pending" | "confirmed",
        }
        """
        ...

    @abstractmethod
    async def verify_webhook(self, payload: dict, signature: str) -> dict:
        """Верифицировать и распарсить вебхук.

        Args:
            payload: тело запроса
            signature: значение заголовка X-Webhook-Secret

        Returns:
            {
                "order_id": str,
                "payment_provider_id": str,
                "status": "succeeded" | "failed",
                "amount_rub": int,
            }
        """
        ...

    @abstractmethod
    async def cancel_subscription(self, user_id: str) -> bool:
        """Отменить рекуррентные платежи."""
        ...


class StubPaymentProvider(PaymentProvider):
    """Stub-провайдер для разработки. Подтверждает все платежи мгновенно."""

    def __init__(self):
        self._payments: dict[str, dict] = {}

    async def create_payment(
        self,
        order_id: str,
        user_id: str,
        tier_id: str,
        period: str,
        price_rub: int,
    ) -> dict:
        provider_id = f"stub_pay_{uuid.uuid4().hex[:12]}"

        self._payments[provider_id] = {
            "order_id": order_id,
            "user_id": user_id,
            "tier_id": tier_id,
            "period": period,
            "price_rub": price_rub,
        }

        logger.info(
            "STUB PAYMENT: order=%s user=%s tier=%s price=%d provider_id=%s (auto-confirmed)",
            order_id, user_id, tier_id, price_rub, provider_id,
        )

        return {
            "payment_provider_id": provider_id,
            "payment_url": None,
            "status": "confirmed",
        }

    async def verify_webhook(self, payload: dict, signature: str) -> dict:
        """Stub верификация. Проверяет секрет и наличие payment_provider_id."""
        expected_secret = settings.WEBHOOK_SECRET
        if expected_secret and signature != expected_secret:
            raise ValueError("Invalid webhook signature")

        provider_id = payload.get("payment_provider_id", "")
        payment = self._payments.get(provider_id)

        if not payment:
            raise ValueError(f"Unknown payment_provider_id: {provider_id}")

        return {
            "order_id": payment["order_id"],
            "payment_provider_id": provider_id,
            "status": "succeeded",
            "amount_rub": payment["price_rub"],
        }

    async def cancel_subscription(self, user_id: str) -> bool:
        logger.info("STUB CANCEL: user=%s (auto-confirmed)", user_id)
        return True


# --- Активация / деактивация ---

async def activate_subscription(
    user: User,
    tier_id: str,
    period: str,
    order_id: str,
    amount_rub: int,
    db: AsyncSession,
    payment_provider_id: str | None = None,
) -> User:
    """Активировать или продлить подписку.

    Идемпотентность: если order_id уже был активирован, повторная активация пропускается.
    """
    # Проверка идемпотентности
    if await is_payment_already_processed(order_id, db):
        logger.warning(
            "Повторная активация пропущена (идемпотентность): order=%s user=%s",
            order_id, user.id,
        )
        return user

    duration = get_subscription_duration(period)
    now = datetime.now(timezone.utc)

    # Продление если активна, иначе с текущего момента
    if user.subscription_expires and user.subscription_expires > now:
        new_expires = user.subscription_expires + duration
    else:
        new_expires = now + duration

    user.subscription_tier = tier_id
    user.subscription_expires = new_expires
    user.subscription_auto_renew = True

    db.add(user)

    # Запись в реестр
    await log_event(
        user_id=user.id,
        event_type=SubscriptionEventType.ACTIVATED,
        order_id=order_id,
        tier_id=tier_id,
        period=period,
        amount_rub=amount_rub,
        status="confirmed",
        db=db,
        payment_provider_id=payment_provider_id,
    )

    await db.commit()
    await db.refresh(user)

    logger.info(
        "Подписка активирована: user=%s tier=%s expires=%s order=%s",
        user.id, tier_id, new_expires.isoformat(), order_id,
    )
    return user


async def deactivate_subscription(
    user: User,
    db: AsyncSession,
) -> User:
    """Отменить подписку. Доступ сохраняется до истечения срока."""
    user.subscription_auto_renew = False

    db.add(user)

    # Запись в реестр
    await log_event(
        user_id=user.id,
        event_type=SubscriptionEventType.CANCELLED,
        order_id=f"cancel_{uuid.uuid4().hex[:12]}",
        tier_id=user.subscription_tier,
        period="",
        amount_rub=0,
        status="cancelled",
        db=db,
    )

    await db.commit()
    await db.refresh(user)

    logger.info(
        "Подписка отменена: user=%s tier=%s expires=%s (доступ сохранен)",
        user.id, user.subscription_tier,
        user.subscription_expires.isoformat() if user.subscription_expires else "none",
    )
    return user


# --- Singleton ---
payment_provider = StubPaymentProvider()
