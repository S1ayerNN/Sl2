"""Subscription API -- безопасная обработка подписок.

Безопасность:
- Rate limiting на subscribe (5 попыток/час)
- Защита от даунгрейда (premium -> plus заблокирован)
- Идемпотентность вебхуков (дублирующие payment_id игнорируются)
- Webhook auth через X-Webhook-Secret
- Реестр подписок (subscription_events) -- все операции записываются
- Верификация суммы при вебхуке
- Webhook не раскрывает существование пользователей (всегда 200)
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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
    check_subscribe_rate_limit,
    create_order,
    deactivate_subscription,
    find_order_by_provider_id,
    get_price,
    is_downgrade,
    is_payment_already_processed,
    log_event,
    payment_provider,
)
from app.models.subscription import SubscriptionEventType
from app.services.tier_config import get_tier_config, TIER_CONFIGS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscription", tags=["Subscription"])


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(
    request: SubscribeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Оформить подписку.

    Stub-режим: активация мгновенная (без оплаты).
    Продакшен: возвращает payment_url для редиректа на шлюз.

    Защита:
    - Rate limit: макс 5 попыток/час
    - Нельзя подписаться на free
    - Нельзя даунгрейднуть (premium -> plus)
    - Нельзя подписаться на тот же активный тариф
    """
    tier_id = request.tier_id
    period = request.period

    # Rate limiting
    within_limit = await check_subscribe_rate_limit(str(current_user.id))
    if not within_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток подписки. Попробуйте через час.",
        )

    # Валидация тарифа
    if tier_id not in TIER_CONFIGS or tier_id == "free":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неверный тариф: {tier_id}. Выберите 'plus' или 'premium'.",
        )

    # Валидация периода
    if period not in ("month", "year"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный период. Выберите 'month' или 'year'.",
        )

    # Защита от даунгрейда
    if current_user.has_active_subscription and is_downgrade(current_user.subscription_tier, tier_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Нельзя перейти с {current_user.subscription_tier} на {tier_id}. "
                   "Дождитесь окончания текущей подписки или обратитесь в поддержку.",
        )

    # Проверка на дублирующую подписку
    if (
        current_user.subscription_tier == tier_id
        and current_user.subscription_expires
        and current_user.subscription_expires > datetime.now(timezone.utc)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"У вас уже активна подписка {tier_id} до "
                   f"{current_user.subscription_expires.strftime('%d.%m.%Y')}. "
                   "Она будет продлена при следующем платеже.",
        )

    # Рассчитать цену
    try:
        price = get_price(tier_id, period)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Создать заказ в реестре
    order = await create_order(
        user_id=current_user.id,
        tier_id=tier_id,
        period=period,
        amount_rub=price,
        db=db,
    )

    # Создать платеж через провайдер
    payment_result = await payment_provider.create_payment(
        order_id=order.order_id,
        user_id=str(current_user.id),
        tier_id=tier_id,
        period=period,
        price_rub=price,
    )

    # Обновить order с provider_id
    order.payment_provider_id = payment_result["payment_provider_id"]
    db.add(order)
    await db.commit()

    # Stub: автоподтверждение -- активировать сразу
    if payment_result["status"] == "confirmed":
        await activate_subscription(
            current_user, tier_id, period,
            order_id=order.order_id,
            amount_rub=price,
            db=db,
            payment_provider_id=payment_result["payment_provider_id"],
        )

        tier_config = get_tier_config(tier_id)
        return SubscribeResponse(
            status="activated",
            order_id=order.order_id,
            tier_id=tier_id,
            period=period,
            price_rub=price,
            message=f"Подписка {tier_config.display_name} активирована! "
                    f"(Stub-режим: оплата не списана)",
        )

    # Продакшен: вернуть URL для оплаты
    return SubscribeResponse(
        status="pending_payment",
        order_id=order.order_id,
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
    """Текущий статус подписки."""
    tier = get_tier_config(current_user.subscription_tier)

    return SubscriptionStatusResponse(
        tier_id=current_user.subscription_tier,
        display_name=tier.display_name,
        is_active=current_user.has_active_subscription,
        expires_at=current_user.subscription_expires,
        auto_renew=current_user.subscription_auto_renew,
        can_cancel=current_user.has_active_subscription,
    )


@router.post("/cancel", response_model=CancelSubscriptionResponse)
async def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Отменить подписку. Доступ сохраняется до истечения срока."""
    if not current_user.has_active_subscription:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нет активной подписки для отмены.",
        )

    # Отменить рекуррентные платежи у провайдера
    await payment_provider.cancel_subscription(str(current_user.id))

    # Записать отмену в реестр + обновить auto_renew
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
    x_webhook_secret: str = Header(default="", alias="X-Webhook-Secret"),
):
    """Вебхук от платежного провайдера.

    Безопасность:
    - Проверка X-Webhook-Secret (WEBHOOK_SECRET из конфига)
    - Идемпотентность: повторные вебхуки для того же платежа игнорируются
    - Верификация суммы: сумма от провайдера сверяется с заказом
    - Не раскрывает существование пользователей (всегда 200 при ошибках)
    - Все события логируются в реестр
    """
    # Верификация вебхука через провайдер (включает проверку секрета)
    try:
        verified = await payment_provider.verify_webhook(
            payload.model_dump(), x_webhook_secret
        )
    except ValueError as e:
        logger.warning("Ошибка верификации вебхука: %s", e)
        # Не раскрываем детали -- всегда 200 для внешних вебхуков
        return {"status": "error", "message": "Webhook verification failed."}

    order_id = verified["order_id"]
    provider_id = verified["payment_provider_id"]

    # Логируем получение вебхука
    # Ищем заказ по order_id (источник правды для tier_id, period, amount)
    order = await find_order_by_provider_id(provider_id, db)
    if not order:
        logger.warning("Вебхук: заказ не найден для provider_id=%s", provider_id)
        return {"status": "error", "message": "Order not found."}

    # Записываем получение вебхука в реестр
    await log_event(
        user_id=order.user_id,
        event_type=SubscriptionEventType.WEBHOOK_RECEIVED,
        order_id=order.order_id,
        tier_id=order.tier_id,
        period=order.period,
        amount_rub=order.amount_rub,
        status=verified["status"],
        db=db,
        payment_provider_id=provider_id,
        meta=f"provider_status={verified['status']}",
    )

    if verified["status"] != "succeeded":
        logger.info("Платеж не прошел: order=%s provider_id=%s", order_id, provider_id)
        await log_event(
            user_id=order.user_id,
            event_type=SubscriptionEventType.PAYMENT_FAILED,
            order_id=order.order_id,
            tier_id=order.tier_id,
            period=order.period,
            amount_rub=order.amount_rub,
            status="failed",
            db=db,
            payment_provider_id=provider_id,
        )
        return {"status": "noted", "message": "Payment was not successful."}

    # Проверка суммы (защита от подмены)
    webhook_amount = verified.get("amount_rub", 0)
    if webhook_amount > 0 and webhook_amount != order.amount_rub:
        logger.error(
            "НЕСОВПАДЕНИЕ СУММЫ: order=%s expected=%d got=%d",
            order.order_id, order.amount_rub, webhook_amount,
        )
        return {"status": "error", "message": "Amount mismatch."}

    # Идемпотентность: проверяем, не был ли уже обработан
    if await is_payment_already_processed(order.order_id, db):
        logger.info("Вебхук: дублирующая обработка пропущена order=%s", order.order_id)
        return {"status": "ok", "message": "Already processed."}

    # Найти пользователя
    result = await db.execute(
        select(User).where(User.id == order.user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        logger.error("Вебхук: пользователь не найден user=%s", order.user_id)
        # НЕ возвращаем 404 -- не раскрываем существование пользователей
        return {"status": "error", "message": "Processing error."}

    # Активация из ДАННЫХ ЗАКАЗА (не из вебхука -- защита от подмены tier_id/period)
    await activate_subscription(
        user,
        tier_id=order.tier_id,
        period=order.period,
        order_id=order.order_id,
        amount_rub=order.amount_rub,
        db=db,
        payment_provider_id=provider_id,
    )

    logger.info(
        "Вебхук: подписка активирована user=%s tier=%s order=%s",
        order.user_id, order.tier_id, order.order_id,
    )

    return {"status": "ok", "message": "Subscription activated."}
