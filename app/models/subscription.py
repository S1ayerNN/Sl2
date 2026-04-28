"""Subscription event model -- реестр подписок.

Хранит все события подписки: создание заказа, оплату, активацию, отмену.
Служит аудит-логом и источником правды для идемпотентности вебхуков.

БЕЗОПАСНОСТЬ:
- Таблица НЕ содержит платежных данных (номер карты, CVV и т.д.)
- Таблица НЕ содержит персональных данных (имя, email)
- payment_provider_id -- это опаке-идентификатор от провайдера (не PII)
- user_id -- это UUID (не PII)
"""

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SubscriptionEventType(str, PyEnum):
    """Типы событий подписки."""
    ORDER_CREATED = "order_created"      # Заказ создан (ожидает оплаты)
    PAYMENT_CONFIRMED = "payment_confirmed"  # Оплата подтверждена
    PAYMENT_FAILED = "payment_failed"    # Оплата не прошла
    ACTIVATED = "activated"              # Подписка активирована
    CANCELLED = "cancelled"              # Подписка отменена пользователем
    EXPIRED = "expired"                  # Подписка истекла
    WEBHOOK_RECEIVED = "webhook_received"  # Вебхук получен (для аудита)


class SubscriptionEvent(Base):
    """Реестр событий подписки.

    Каждая строка -- одно событие в жизненном цикле подписки.
    Ничего не удаляется -- append-only audit log.

    Содержит ТОЛЬКО:
    - UUID пользователя (не PII)
    - Идентификаторы тарифа и периода (бизнес-данные)
    - Суммы в рублях (не привязаны к конкретному платежному средству)
    - Опаке-идентификатор платежа от провайдера (не PII)
    """
    __tablename__ = "subscription_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Связь с пользователем (UUID, не PII)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # Тип события
    event_type: Mapped[str] = mapped_column(String(30), index=True)

    # Детали заказа (фиксируются при создании, не меняются)
    tier_id: Mapped[str] = mapped_column(String(20))  # "plus" / "premium"
    period: Mapped[str] = mapped_column(String(10))    # "month" / "year"
    amount_rub: Mapped[int] = mapped_column(Integer)   # Сумма в рублях

    # Идентификатор платежа
    # Внутренний ID нашего заказа (для идемпотентности)
    order_id: Mapped[str] = mapped_column(String(64), index=True)
    # ID платежа у провайдера (опаке-строка, не PII)
    payment_provider_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )

    # Статус
    status: Mapped[str] = mapped_column(String(20))  # pending / confirmed / failed / cancelled

    # Метаданные (НЕ содержит PII -- только технические данные)
    # Например: provider name, error code, webhook event type
    meta: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Время события
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationship
    user = relationship("User", backref="subscription_events")
