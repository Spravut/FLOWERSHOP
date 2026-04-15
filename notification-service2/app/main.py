from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path as SysPath
from typing import Any, Dict, List, Optional

import aiofiles
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Path, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_sessionmaker
from app.nats_consumer import run_nats_consumer
from app.models import (
    ClientSubscription as ClientSubscriptionModel,
    DashboardView as DashboardViewModel,
    Notification as NotificationModel,
    NotificationChannel,
    OrderStatus,
    PromoNotification as PromoNotificationModel,
    PromoStatus,
    ReportTask as ReportTaskModel,
    ReportTaskStatus,
    TargetAudience,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer_task = asyncio.create_task(run_nats_consumer())
    yield
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Notification Service API",
    description="Сервис уведомлений о статусах заказов и акционных предложениях",
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

REPORTS_DIR = SysPath(os.getenv("REPORTS_DIR", "generated_reports"))
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

class Metadata(BaseModel):
    courier_name: Optional[str] = Field(None)
    estimated_minutes: Optional[int] = Field(None)
    tracking_number: Optional[str] = Field(None)
    courier_phone: Optional[str] = Field(None)

class NotificationCreate(BaseModel):
    status: OrderStatus
    channel: NotificationChannel
    custom_message: Optional[str] = Field(None)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class NotificationUpdate(BaseModel):
    status: Optional[OrderStatus] = None
    channel: Optional[NotificationChannel] = None
    message: Optional[str] = Field(None)
    metadata: Optional[Dict[str, Any]] = None
    read: Optional[bool] = Field(None)

class Notification(BaseModel):
    id: str
    order_id: Optional[str] = None
    client_id: str
    status: OrderStatus
    channel: NotificationChannel
    message: str
    metadata: Optional[Dict[str, Any]] = None
    sent_at: datetime
    read_at: Optional[datetime] = None
    estimated_delivery_time: Optional[datetime] = None
    courier_name: Optional[str] = None
    tracking_url: Optional[str] = None

    @classmethod
    def model_validate(cls, obj, **kwargs):
        if hasattr(obj, 'meta_data'):
            data = {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
            if 'meta_data' in data:
                data['metadata'] = data.pop('meta_data')
            return super().model_validate(data, **kwargs)
        return super().model_validate(obj, **kwargs)

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "notif_123456",
                "order_id": "123e4567-e89b-12d3-a456-426614174000",
                "client_id": "123e4567-e89b-12d3-a456-426614174001",
                "status": "out_for_delivery",
                "message": "🛵 Ваш заказ в пути! Курьер Алексей будет через 30 минут",
                "channel": "sms",
                "sent_at": "2024-01-15T14:30:00",
                "courier_name": "Алексей",
                "estimated_delivery_time": "2024-01-15T15:00:00"
            }
        }

class PromoNotificationCreate(BaseModel):
    title: str = Field(..., max_length=200)
    message: str = Field(..., max_length=1000)
    promo_code: Optional[str] = Field(None)
    discount_percent: Optional[int] = Field(None, ge=0, le=100)
    image_url: Optional[str] = Field(None)
    start_date: datetime
    end_date: datetime
    target_audience: TargetAudience = TargetAudience.ALL
    channels: List[str] = Field(default_factory=lambda: ["email", "push"])
    scheduled_for: Optional[datetime] = None


class PromoNotificationUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    message: Optional[str] = Field(None, max_length=1000)
    promo_code: Optional[str] = None
    discount_percent: Optional[int] = Field(None, ge=0, le=100)
    image_url: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    target_audience: Optional[TargetAudience] = None
    channels: Optional[List[str]] = None
    status: Optional[PromoStatus] = None
    scheduled_for: Optional[datetime] = None

class PromoNotification(BaseModel):
    id: str
    title: str
    message: str
    promo_code: Optional[str] = None
    discount_percent: Optional[int] = None
    image_url: Optional[str] = None
    start_date: datetime
    end_date: datetime
    target_audience: TargetAudience
    channels: List[str]
    status: PromoStatus
    scheduled_for: Optional[datetime] = None
    sent_count: int
    created_at: datetime
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "promo_123456",
                "title": "☀️ Летняя распродажа 50%",
                "message": "Только этим летом — скидка 50% на все букеты! Успейте порадовать близких по суперцене.",
                "promo_code": "SUMMER50",
                "discount_percent": 50,
                "image_url": "https://example.com/images/summer-sale.png",
                "start_date": "2026-06-01T09:00:00",
                "end_date": "2026-06-30T21:00:00",
                "status": "scheduled",
                "sent_count": 0
            }
        }

class ChannelSubscriptions(BaseModel):
    """Подписки по каналам для конкретного типа уведомлений"""
    sms: bool = False
    email: bool = True
    push: bool = True
    telegram: bool = False

class QuietHours(BaseModel):
    """Тихие часы (не беспокоить)"""
    enabled: bool = False
    start: Optional[str] = Field(None, pattern="^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$", example="22:00")
    end: Optional[str] = Field(None, pattern="^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$", example="09:00")

class ClientSubscriptions(BaseModel):
    """Настройки подписок клиента"""
    client_id: str
    order_notifications: ChannelSubscriptions
    promo_notifications: ChannelSubscriptions
    quiet_hours: QuietHours
    updated_at: datetime
    
    class Config:
        from_attributes = True

class ClientSubscriptionsUpdate(BaseModel):
    """Модель для обновления подписок"""
    order_notifications: Optional[Dict[str, bool]] = None
    promo_notifications: Optional[Dict[str, bool]] = None
    quiet_hours: Optional[Dict[str, Any]] = None

class NotificationStats(BaseModel):
    """Статистика по уведомлениям"""
    period: str
    total_sent: int
    by_channel: Dict[str, int]
    by_type: Dict[str, int]
    open_rate: float
    delivery_rate: float

class ReportExportRequest(BaseModel):
    """Модель для запроса на экспорт отчёта"""
    date_from: Optional[datetime] = Field(None, description="Начальная дата")
    date_to: Optional[datetime] = Field(None, description="Конечная дата")
    channel: Optional[NotificationChannel] = Field(None, description="Фильтр по каналу")
    status: Optional[OrderStatus] = Field(None, description="Фильтр по статусу")

class ReportTaskCreateResponse(BaseModel):
    task_id: str
    status_url: str
    result_url: str

class ReportTaskStatusResponse(BaseModel):
    task_id: str
    kind: str
    status: ReportTaskStatus
    progress: int
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result_file: Optional[str] = None
    error_message: Optional[str] = None

def generate_status_message(order_id: str, status: OrderStatus, metadata: Optional[Dict] = None) -> str:
    """Генерирует сообщение в зависимости от статуса заказа"""
    messages = {
        OrderStatus.CONFIRMED: f"✅ Заказ №{order_id[:8]} подтвержден! Начинаем собирать букет.",
        OrderStatus.GATHERING: f"👩‍🌾 Флорист собирает ваш букет для заказа №{order_id[:8]}",
        OrderStatus.READY_FOR_DELIVERY: f"📦 Заказ №{order_id[:8]} готов к доставке!",
        OrderStatus.COURIER_ASSIGNED: f"🚚 Курьер назначен для заказа №{order_id[:8]}",
        OrderStatus.OUT_FOR_DELIVERY: f"🛵 Курьер выехал с вашим заказом №{order_id[:8]}!",
        OrderStatus.DELIVERED: f"🎉 Заказ №{order_id[:8]} доставлен! Спасибо за покупку!",
        OrderStatus.CANCELLED: f"❌ Заказ №{order_id[:8]} отменен"
    }
    
    base_msg = messages.get(status, f"Статус заказа №{order_id[:8]} изменен: {status.value}")
    
    if metadata and status == OrderStatus.OUT_FOR_DELIVERY:
        if metadata.get('courier_name'):
            base_msg += f" Курьер: {metadata['courier_name']}."
        if metadata.get('estimated_minutes'):
            base_msg += f" Будет через {metadata['estimated_minutes']} мин."
    
    return base_msg

def convert_subscription_to_pydantic(db_sub: ClientSubscriptionModel) -> ClientSubscriptions:
    """Конвертирует модель БД в Pydantic схему"""
    return ClientSubscriptions(
        client_id=db_sub.client_id,
        order_notifications=ChannelSubscriptions(
            sms=db_sub.order_sms,
            email=db_sub.order_email,
            push=db_sub.order_push,
            telegram=db_sub.order_telegram
        ),
        promo_notifications=ChannelSubscriptions(
            sms=db_sub.promo_sms,
            email=db_sub.promo_email,
            push=db_sub.promo_push,
            telegram=db_sub.promo_telegram
        ),
        quiet_hours=QuietHours(
            enabled=db_sub.quiet_hours_enabled,
            start=db_sub.quiet_hours_start,
            end=db_sub.quiet_hours_end
        ),
        updated_at=db_sub.updated_at or db_sub.created_at
    )

async def _set_task_state(
    session: AsyncSession,
    task_id: str,
    *,
    status: Optional[ReportTaskStatus] = None,
    progress: Optional[int] = None,
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
    result_file: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    res = await session.execute(select(ReportTaskModel).where(ReportTaskModel.id == task_id))
    task = res.scalar_one_or_none()
    if task is None:
        return
    if status is not None:
        task.status = status
    if progress is not None:
        task.progress = max(0, min(100, int(progress)))
    if started_at is not None:
        task.started_at = started_at
    if finished_at is not None:
        task.finished_at = finished_at
    if result_file is not None:
        task.result_file = result_file
    if error_message is not None:
        task.error_message = error_message
    await session.commit()

async def _generate_export_notifications_json(task_id: str, filters: Optional[ReportExportRequest] = None) -> None:
    """Генерирует отчёт с учётом фильтров"""
    sessionmaker = get_sessionmaker()
    
    try:
        async with sessionmaker() as session:
            await _set_task_state(
                session, task_id, status=ReportTaskStatus.RUNNING, progress=1, started_at=datetime.now(timezone.utc)
            )
        
        async with sessionmaker() as session:
            query = select(NotificationModel).order_by(NotificationModel.sent_at.asc())
            
            if filters:
                if filters.date_from:
                    query = query.where(NotificationModel.sent_at >= filters.date_from)
                if filters.date_to:
                    query = query.where(NotificationModel.sent_at <= filters.date_to)
                if filters.channel:
                    query = query.where(NotificationModel.channel == filters.channel)
                if filters.status:
                    query = query.where(NotificationModel.status == filters.status)
            
            res = await session.execute(query)
            notifications = res.scalars().all()
            
            await _set_task_state(session, task_id, progress=35)

        report_data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "filters": filters.dict() if filters else {},
            "total_count": len(notifications),
            "notifications": [Notification.model_validate(n).model_dump(mode="json") for n in notifications]
        }

        file_name = f"{task_id}.notifications.json"
        file_path = REPORTS_DIR / file_name
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(report_data, ensure_ascii=False, indent=2))

        async with sessionmaker() as session:
            await _set_task_state(
                session,
                task_id,
                status=ReportTaskStatus.COMPLETED,
                progress=100,
                finished_at=datetime.now(timezone.utc),
                result_file=file_name,
            )
            
    except Exception as e:
        async with sessionmaker() as session:
            await _set_task_state(
                session,
                task_id,
                status=ReportTaskStatus.FAILED,
                progress=100,
                finished_at=datetime.now(timezone.utc),
                error_message=str(e),
            )
        logger.exception("Error generating report for task %s: %s", task_id, e)

async def _load_profile(user_id: str) -> Dict[str, Any]:
    await asyncio.sleep(0.15)
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        res = await session.execute(
            select(ClientSubscriptionModel).where(ClientSubscriptionModel.client_id == user_id)
        )
        sub = res.scalar_one_or_none()
        return {
            "user_id": user_id,
            "has_subscriptions": sub is not None,
            "quiet_hours_enabled": bool(sub.quiet_hours_enabled) if sub else False,
        }

async def _load_activity(user_id: str) -> Dict[str, Any]:
    await asyncio.sleep(0.15)
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        total = await session.scalar(
            select(func.count()).select_from(NotificationModel).where(NotificationModel.client_id == user_id)
        )
        unread = await session.scalar(
            select(func.count())
            .select_from(NotificationModel)
            .where(and_(NotificationModel.client_id == user_id, NotificationModel.read_at.is_(None)))
        )
        return {"total_notifications": int(total or 0), "unread_notifications": int(unread or 0)}

async def _load_recommendations() -> Dict[str, Any]:
    await asyncio.sleep(0.15)
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        res = await session.execute(
            select(PromoNotificationModel).order_by(PromoNotificationModel.created_at.desc()).limit(3)
        )
        promos = res.scalars().all()
        return {
            "top_promos": [
                {"id": p.id, "title": p.title, "status": p.status.value if p.status else None} for p in promos
            ]
        }

def _log_dashboard_view_to_file(user_id: str) -> None:
    line = f"{datetime.utcnow().isoformat()}Z user_id={user_id}\n"
    with open(REPORTS_DIR / "dashboard_views.log", "a", encoding="utf-8") as f:
        f.write(line)

@app.get("/")
async def root():
    """Корневой эндпоинт для проверки работоспособности"""
    return {
        "message": "Notification Service API",
        "status": "running",
        "version": "1.1.0",
        "docs": "/docs",
        "endpoints": {
            "order_notifications": "/orders/{orderId}/notifications",
            "promo_notifications": "/promo/notifications",
            "subscriptions": "/clients/{clientId}/subscriptions",
            "stats": "/notifications/stats"
        }
    }

@app.get("/orders/{order_id}/notifications", response_model=Dict[str, Any])
async def get_order_notifications(
    order_id: str = Path(..., description="ID заказа"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Получить историю уведомлений по заказу.
    Возвращает все уведомления, отправленные по конкретному заказу.
    """
    total = await db.scalar(
        select(func.count()).select_from(NotificationModel).where(NotificationModel.order_id == order_id)
    )
    res = await db.execute(
        select(NotificationModel)
        .where(NotificationModel.order_id == order_id)
        .order_by(NotificationModel.sent_at.desc())
        .offset(offset)
        .limit(limit)
    )
    notifications = res.scalars().all()

    return {
        "items": [Notification.model_validate(n) for n in notifications],
        "total": int(total or 0),
        "limit": limit,
        "offset": offset
    }


@app.get("/notifications", response_model=Dict[str, Any])
async def list_notifications(
    client_id: Optional[str] = Query(None, description="Фильтр по ID клиента"),
    status: Optional[OrderStatus] = Query(None, description="Фильтр по статусу заказа"),
    channel: Optional[NotificationChannel] = Query(None, description="Фильтр по каналу"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Получить список всех уведомлений с фильтрами и пагинацией.
    """
    conditions = []
    if client_id:
        conditions.append(NotificationModel.client_id == client_id)
    if status:
        conditions.append(NotificationModel.status == status)
    if channel:
        conditions.append(NotificationModel.channel == channel)

    where_clause = and_(*conditions) if conditions else None

    total_stmt = select(func.count()).select_from(NotificationModel)
    if where_clause is not None:
        total_stmt = total_stmt.where(where_clause)
    total = await db.scalar(total_stmt)

    stmt = select(NotificationModel).order_by(NotificationModel.sent_at.desc()).offset(offset).limit(limit)
    if where_clause is not None:
        stmt = stmt.where(where_clause)
    res = await db.execute(stmt)
    notifications = res.scalars().all()

    return {
        "items": [Notification.model_validate(n) for n in notifications],
        "total": int(total or 0),
        "limit": limit,
        "offset": offset,
    }

@app.post("/orders/{order_id}/notifications", response_model=Notification, status_code=201)
async def create_order_notification(
    order_id: str,
    notification: NotificationCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Отправить уведомление о смене статуса заказа.
    Создаёт и отправляет уведомление клиенту об изменении статуса заказа.
    """
    client_id = f"client_{hash(order_id) % 1000}"

    if notification.custom_message:
        message = notification.custom_message
    else:
        message = generate_status_message(order_id, notification.status, notification.metadata)
    
    courier_name = None
    estimated_delivery_time = None
    
    if notification.status == OrderStatus.OUT_FOR_DELIVERY and notification.metadata:
        courier_name = notification.metadata.get('courier_name')
        if notification.metadata.get('estimated_minutes'):
            estimated_delivery_time = datetime.now() + timedelta(
                minutes=notification.metadata['estimated_minutes']
            )
    
    notification_id = f"notif_{uuid.uuid4().hex[:8]}"

    db_notification = NotificationModel(
        id=notification_id,
        order_id=order_id,
        client_id=client_id,
        status=notification.status,
        channel=notification.channel,
        message=message,
        meta_data=notification.metadata,
        courier_name=courier_name,
        estimated_delivery_time=estimated_delivery_time
    )
    
    db.add(db_notification)
    await db.commit()
    await db.refresh(db_notification)
    
    return Notification.model_validate(db_notification)

@app.get("/notifications/{notification_id}", response_model=Notification)
async def get_notification(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Получить детали обычного уведомления по ID.
    """
    res = await db.execute(select(NotificationModel).where(NotificationModel.id == notification_id))
    notification = res.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    return Notification.model_validate(notification)


@app.put("/notifications/{notification_id}", response_model=Notification)
async def update_notification(
    notification_id: str,
    data: NotificationUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Обновить уведомление (статус, канал, текст, метаданные, признак прочитанности).
    """
    res = await db.execute(select(NotificationModel).where(NotificationModel.id == notification_id))
    notification = res.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    if data.status is not None:
        notification.status = data.status
    if data.channel is not None:
        notification.channel = data.channel
    if data.message is not None:
        notification.message = data.message
    if data.metadata is not None:
        notification.meta_data = data.metadata
    if data.read is not None:
        notification.read_at = datetime.now() if data.read else None

    await db.commit()
    await db.refresh(notification)

    return Notification.model_validate(notification)


@app.delete("/notifications/{notification_id}", status_code=204)
async def delete_notification(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Удалить уведомление по ID.
    """
    res = await db.execute(select(NotificationModel).where(NotificationModel.id == notification_id))
    notification = res.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    await db.delete(notification)
    await db.commit()

    return None

@app.post("/promo/notifications", response_model=PromoNotification, status_code=202)
async def create_promo_notification(
    promo: PromoNotificationCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Создать акционное уведомление.
    Создаёт уведомление об акции для рассылки подписанным клиентам.
    """
    promo_id = f"promo_{uuid.uuid4().hex[:8]}"

    status = PromoStatus.SCHEDULED if promo.scheduled_for else PromoStatus.SENDING
    
    db_promo = PromoNotificationModel(
        id=promo_id,
        title=promo.title,
        message=promo.message,
        promo_code=promo.promo_code,
        discount_percent=promo.discount_percent,
        image_url=promo.image_url,
        start_date=promo.start_date,
        end_date=promo.end_date,
        target_audience=promo.target_audience,
        channels=promo.channels,
        status=status,
        scheduled_for=promo.scheduled_for,
        sent_count=0
    )
    
    db.add(db_promo)
    await db.commit()
    await db.refresh(db_promo)
    
    return PromoNotification.model_validate(db_promo)

@app.get("/promo/notifications", response_model=List[PromoNotification])
async def get_promo_notifications(
    status: Optional[PromoStatus] = Query(None),
    from_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Получить список акционных уведомлений.
    Возвращает историю акционных рассылок с возможностью фильтрации.
    """
    conditions = []
    if status:
        conditions.append(PromoNotificationModel.status == status)
    if from_date:
        conditions.append(PromoNotificationModel.created_at >= from_date)

    stmt = select(PromoNotificationModel).order_by(PromoNotificationModel.created_at.desc())
    if conditions:
        stmt = stmt.where(and_(*conditions))
    res = await db.execute(stmt)
    promos = res.scalars().all()

    return [PromoNotification.model_validate(p) for p in promos]


@app.get("/promo/notifications/{promo_id}", response_model=PromoNotification)
async def get_promo_notification(
    promo_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Получить одно акционное уведомление по ID.
    """
    res = await db.execute(select(PromoNotificationModel).where(PromoNotificationModel.id == promo_id))
    promo = res.scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=404, detail="Promo notification not found")

    return PromoNotification.model_validate(promo)


@app.put("/promo/notifications/{promo_id}", response_model=PromoNotification)
async def update_promo_notification(
    promo_id: str,
    data: PromoNotificationUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Обновить акционное уведомление.
    """
    res = await db.execute(select(PromoNotificationModel).where(PromoNotificationModel.id == promo_id))
    promo = res.scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=404, detail="Promo notification not found")

    if data.title is not None:
        promo.title = data.title
    if data.message is not None:
        promo.message = data.message
    if data.promo_code is not None:
        promo.promo_code = data.promo_code
    if data.discount_percent is not None:
        promo.discount_percent = data.discount_percent
    if data.image_url is not None:
        promo.image_url = data.image_url
    if data.start_date is not None:
        promo.start_date = data.start_date
    if data.end_date is not None:
        promo.end_date = data.end_date
    if data.target_audience is not None:
        promo.target_audience = data.target_audience
    if data.channels is not None:
        promo.channels = data.channels
    if data.status is not None:
        promo.status = data.status
    if data.scheduled_for is not None:
        promo.scheduled_for = data.scheduled_for

    await db.commit()
    await db.refresh(promo)

    return PromoNotification.model_validate(promo)


@app.delete("/promo/notifications/{promo_id}", status_code=204)
async def delete_promo_notification(
    promo_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Удалить акционное уведомление по ID.
    """
    res = await db.execute(select(PromoNotificationModel).where(PromoNotificationModel.id == promo_id))
    promo = res.scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=404, detail="Promo notification not found")

    await db.delete(promo)
    await db.commit()

    return None

@app.get("/clients/{client_id}/subscriptions", response_model=ClientSubscriptions)
async def get_client_subscriptions(
    client_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Получить настройки подписок клиента.
    """
    res = await db.execute(
        select(ClientSubscriptionModel).where(ClientSubscriptionModel.client_id == client_id)
    )
    subscription = res.scalar_one_or_none()
    
    if not subscription:
        subscription = ClientSubscriptionModel(client_id=client_id)
        db.add(subscription)
        await db.commit()
        await db.refresh(subscription)
    
    return convert_subscription_to_pydantic(subscription)

@app.put("/clients/{client_id}/subscriptions", response_model=ClientSubscriptions)
async def update_client_subscriptions(
    client_id: str,
    update: ClientSubscriptionsUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Обновить подписки клиента.
    """
    res = await db.execute(
        select(ClientSubscriptionModel).where(ClientSubscriptionModel.client_id == client_id)
    )
    subscription = res.scalar_one_or_none()
    
    if not subscription:
        subscription = ClientSubscriptionModel(client_id=client_id)
        db.add(subscription)
    
    if update.order_notifications:
        if 'sms' in update.order_notifications:
            subscription.order_sms = update.order_notifications['sms']
        if 'email' in update.order_notifications:
            subscription.order_email = update.order_notifications['email']
        if 'push' in update.order_notifications:
            subscription.order_push = update.order_notifications['push']
        if 'telegram' in update.order_notifications:
            subscription.order_telegram = update.order_notifications['telegram']
    
    if update.promo_notifications:
        if 'sms' in update.promo_notifications:
            subscription.promo_sms = update.promo_notifications['sms']
        if 'email' in update.promo_notifications:
            subscription.promo_email = update.promo_notifications['email']
        if 'push' in update.promo_notifications:
            subscription.promo_push = update.promo_notifications['push']
        if 'telegram' in update.promo_notifications:
            subscription.promo_telegram = update.promo_notifications['telegram']
    
    if update.quiet_hours:
        if 'enabled' in update.quiet_hours:
            subscription.quiet_hours_enabled = update.quiet_hours['enabled']
        if 'start' in update.quiet_hours:
            subscription.quiet_hours_start = update.quiet_hours['start']
        if 'end' in update.quiet_hours:
            subscription.quiet_hours_end = update.quiet_hours['end']
    
    await db.commit()
    await db.refresh(subscription)
    
    return convert_subscription_to_pydantic(subscription)


@app.delete("/clients/{client_id}/subscriptions", status_code=204)
async def delete_client_subscriptions(
    client_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Удалить настройки подписок клиента.
    """
    res = await db.execute(
        select(ClientSubscriptionModel).where(ClientSubscriptionModel.client_id == client_id)
    )
    subscription = res.scalar_one_or_none()
    if not subscription:
        raise HTTPException(status_code=404, detail="Client subscriptions not found")

    await db.delete(subscription)
    await db.commit()

    return None

@app.get("/notifications/stats", response_model=NotificationStats)
async def get_notification_stats(
    period: str = Query("week", enum=["day", "week", "month"]),
    db: AsyncSession = Depends(get_db),
):
    """
    Получить статистику по уведомлениям за указанный период.
    """
    now = datetime.now()
    
    if period == "day":
        start_date = now - timedelta(days=1)
    elif period == "week":
        start_date = now - timedelta(weeks=1)
    else:  # month
        start_date = now - timedelta(days=30)
    
    res_n = await db.execute(select(NotificationModel).where(NotificationModel.sent_at >= start_date))
    recent_notifications = res_n.scalars().all()

    res_p = await db.execute(
        select(PromoNotificationModel).where(PromoNotificationModel.created_at >= start_date)
    )
    recent_promo = res_p.scalars().all()

    by_channel = {
        "sms": sum(1 for n in recent_notifications if n.channel == NotificationChannel.SMS),
        "email": sum(1 for n in recent_notifications if n.channel == NotificationChannel.EMAIL),
        "push": sum(1 for n in recent_notifications if n.channel == NotificationChannel.PUSH),
        "telegram": sum(1 for n in recent_notifications if n.channel == NotificationChannel.TELEGRAM),
    }

    read_count = sum(1 for n in recent_notifications if n.read_at is not None)
    open_rate = (read_count / len(recent_notifications) * 100) if recent_notifications else 0.0

    stats = NotificationStats(
        period=period,
        total_sent=len(recent_notifications) + sum(p.sent_count for p in recent_promo),
        by_channel=by_channel,
        by_type={
            "order_status": len(recent_notifications),
            "promo": len(recent_promo)
        },
        open_rate=round(open_rate, 2),
        delivery_rate=99.2
    )
    
    return stats

@app.post("/reports/exports/notifications", response_model=ReportTaskCreateResponse, status_code=202)
async def start_export_notifications_report(
    request: Optional[ReportExportRequest] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Экспорт уведомлений в JSON с фильтрацией.
    Возвращает task_id для отслеживания прогресса.
    """
    task_id = f"task_{uuid.uuid4().hex}"
    
    task = ReportTaskModel(
        id=task_id, 
        kind="export_notifications_json", 
        status=ReportTaskStatus.PENDING, 
        progress=0
    )
    db.add(task)
    await db.commit()

    asyncio.create_task(_generate_export_notifications_json(task_id, request))

    return ReportTaskCreateResponse(
        task_id=task_id,
        status_url=f"/reports/tasks/{task_id}",
        result_url=f"/reports/tasks/{task_id}/result",
    )


@app.get("/reports/tasks/{task_id}", response_model=ReportTaskStatusResponse)
async def get_report_task_status(task_id: str, db: AsyncSession = Depends(get_db)):
    """
    Получить статус выполнения задачи по экспорту.
    """
    res = await db.execute(select(ReportTaskModel).where(ReportTaskModel.id == task_id))
    task = res.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return ReportTaskStatusResponse(
        task_id=task.id,
        kind=task.kind,
        status=task.status,
        progress=task.progress,
        created_at=task.created_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
        result_file=task.result_file,
        error_message=task.error_message,
    )


@app.get("/reports/tasks/{task_id}/result")
async def download_report_task_result(task_id: str, db: AsyncSession = Depends(get_db)):
    """
    Скачать результат экспорта (JSON файл).
    """
    res = await db.execute(select(ReportTaskModel).where(ReportTaskModel.id == task_id))
    task = res.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != ReportTaskStatus.COMPLETED or not task.result_file:
        raise HTTPException(status_code=409, detail="Task is not completed yet")

    file_path = REPORTS_DIR / task.result_file
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Result file not found")

    return FileResponse(
        path=str(file_path),
        filename=task.result_file,
        media_type="application/json",
    )

class DashboardResponse(BaseModel):
    user_id: str
    profile: Dict[str, Any]
    activity: Dict[str, Any]
    recommendations: Dict[str, Any]

@app.get("/dashboard/{user_id}", response_model=DashboardResponse)
async def get_dashboard(user_id: str, background_tasks: BackgroundTasks):
    """
    Получить дашборд пользователя с параллельным сбором данных.
    """
    profile, activity, recommendations = await asyncio.gather(
        _load_profile(user_id),
        _load_activity(user_id),
        _load_recommendations(),
    )

    background_tasks.add_task(_log_dashboard_view_to_file, user_id)

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        session.add(DashboardViewModel(user_id=user_id))
        await session.commit()

    return DashboardResponse(
        user_id=user_id,
        profile=profile,
        activity=activity,
        recommendations=recommendations,
    )
