import asyncio
import json
import logging
import threading
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

SUBJECT_ORDER_CREATED = "flowershop.orders.created"
SUBJECT_ORDER_STATUS_CHANGED = "flowershop.orders.status_changed"
STREAM_NAME = "FLOWERSHOP"


def _run_async(coro):
    def _run():
        try:
            asyncio.run(coro)
        except Exception as e:
            logger.exception("NATS publish error: %s", e)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


async def _ensure_stream_and_publish(subject: str, payload: dict) -> None:
    try:
        import nats
        nc = await nats.connect(settings.NATS_URL)
        js = nc.jetstream()

        try:
            await js.add_stream(
                name=STREAM_NAME,
                subjects=["flowershop.orders.>"],
            )
        except Exception:
            pass

        data = json.dumps(payload, ensure_ascii=False).encode()
        await js.publish(subject, data)
        await nc.close()
        logger.info("NATS published to %s: %s", subject, payload.get("order_id", ""))
    except Exception as e:
        logger.exception("NATS publish failed: %s", e)
        raise


def publish_order_created(order) -> None:
    payload = {
        "event": "order.created",
        "order_id": str(order.id),
        "customer_name": order.customer_name,
        "email": order.email,
        "phone": order.phone,
        "total_price": str(order.total_price),
        "status": order.status,
        "user_id": str(order.user_id) if order.user_id else None,
    }
    _run_async(_ensure_stream_and_publish(SUBJECT_ORDER_CREATED, payload))


def publish_order_status_changed(order, old_status: str) -> None:
    status_map = {
        "new": "confirmed",
        "processing": "gathering",
        "delivering": "out_for_delivery",
        "completed": "delivered",
        "cancelled": "cancelled",
    }
    notification_status = status_map.get(order.status, order.status)

    payload = {
        "event": "order.status_changed",
        "order_id": str(order.id),
        "old_status": old_status,
        "new_status": order.status,
        "notification_status": notification_status,
        "customer_name": order.customer_name,
        "email": order.email,
        "user_id": str(order.user_id) if order.user_id else None,
    }
    _run_async(_ensure_stream_and_publish(SUBJECT_ORDER_STATUS_CHANGED, payload))
