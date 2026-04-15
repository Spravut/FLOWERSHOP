from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from app.database import get_sessionmaker
from app.models import Notification, NotificationChannel, OrderStatus

logger = logging.getLogger(__name__)

NATS_URL = os.environ.get("NATS_URL", "nats://localhost:4222")
SUBJECT_ORDERS = "flowershop.orders.>"
STREAM_NAME = "FLOWERSHOP"
CONSUMER_NAME = "notification-service"

STATUS_MAP = {
    "new": OrderStatus.CONFIRMED,
    "confirmed": OrderStatus.CONFIRMED,
    "processing": OrderStatus.GATHERING,
    "gathering": OrderStatus.GATHERING,
    "delivering": OrderStatus.OUT_FOR_DELIVERY,
    "out_for_delivery": OrderStatus.OUT_FOR_DELIVERY,
    "completed": OrderStatus.DELIVERED,
    "delivered": OrderStatus.DELIVERED,
    "cancelled": OrderStatus.CANCELLED,
}


def _status_message(order_id: str, status: OrderStatus) -> str:
    messages = {
        OrderStatus.CONFIRMED: f"✅ Заказ №{order_id} подтверждён! Начинаем собирать букет.",
        OrderStatus.GATHERING: f"👩‍🌾 Флорист собирает ваш букет для заказа №{order_id}",
        OrderStatus.READY_FOR_DELIVERY: f"📦 Заказ №{order_id} готов к доставке!",
        OrderStatus.COURIER_ASSIGNED: f"🚚 Курьер назначен для заказа №{order_id}",
        OrderStatus.OUT_FOR_DELIVERY: f"🛵 Курьер выехал с вашим заказом №{order_id}!",
        OrderStatus.DELIVERED: f"🎉 Заказ №{order_id} доставлен! Спасибо за покупку!",
        OrderStatus.CANCELLED: f"❌ Заказ №{order_id} отменён",
    }
    return messages.get(status, f"Статус заказа №{order_id}: {status.value}")


async def _handle_order_event(payload: dict) -> None:
    event = payload.get("event")
    order_id = payload.get("order_id")
    if not order_id:
        logger.warning("Order event without order_id: %s", payload)
        return

    user_id = payload.get("user_id")
    email = payload.get("email", "")
    client_id = f"user_{user_id}" if user_id else f"email_{email}" or f"order_{order_id}"

    notification_status_str = payload.get("notification_status") or payload.get("status", "confirmed")
    order_status = STATUS_MAP.get(
        str(notification_status_str).lower(),
        OrderStatus.CONFIRMED,
    )

    message = _status_message(order_id, order_status)
    notification_id = f"notif_{uuid.uuid4().hex[:8]}"

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        notification = Notification(
            id=notification_id,
            order_id=str(order_id),
            client_id=client_id,
            status=order_status,
            channel=NotificationChannel.EMAIL,
            message=message,
        )
        session.add(notification)
        await session.commit()
        logger.info(
            "Created notification %s for order %s (event=%s)",
            notification_id,
            order_id,
            event,
        )


async def run_nats_consumer() -> None:
    import nats

    nc = None
    while True:
        try:
            nc = await nats.connect(NATS_URL)
            js = nc.jetstream()

            try:
                await js.add_stream(
                    name=STREAM_NAME,
                    subjects=["flowershop.orders.>"],
                )
            except Exception:
                pass

            psub = await js.pull_subscribe(
                SUBJECT_ORDERS,
                durable=CONSUMER_NAME,
                stream=STREAM_NAME,
            )

            logger.info("NATS consumer started, subscribed to %s", SUBJECT_ORDERS)

            while True:
                try:
                    msgs = await psub.fetch(batch=5, timeout=5.0)
                    for msg in msgs:
                        try:
                            payload = json.loads(msg.data.decode())
                            await _handle_order_event(payload)
                            await msg.ack()
                        except json.JSONDecodeError as e:
                            logger.warning("Invalid JSON in message: %s", e)
                            await msg.ack()
                        except Exception as e:
                            logger.exception("Error handling message: %s", e)
                            await msg.nak()
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.exception("Fetch error: %s", e)
                    break

        except Exception as e:
            logger.exception("NATS connection error: %s", e)

        if nc:
            try:
                await nc.close()
            except Exception:
                pass
            nc = None

        logger.info("Reconnecting to NATS in 10 seconds...")
        await asyncio.sleep(10)
