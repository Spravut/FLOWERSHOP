from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, JSON, Enum as SQLEnum
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum
from app.database import Base

def _enum_values(enum_cls):
    return [e.value for e in enum_cls]


class OrderStatus(str, enum.Enum):
    CONFIRMED = "confirmed"
    GATHERING = "gathering"
    READY_FOR_DELIVERY = "ready_for_delivery"
    COURIER_ASSIGNED = "courier_assigned"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class NotificationChannel(str, enum.Enum):
    SMS = "sms"
    EMAIL = "email"
    PUSH = "push"
    TELEGRAM = "telegram"

class PromoStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    CANCELLED = "cancelled"

class TargetAudience(str, enum.Enum):
    ALL = "all"
    REGULAR_CLIENTS = "regular_clients"
    NEW_CLIENTS = "new_clients"
    BIRTHDAY = "birthday"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String, primary_key=True, default=lambda: f"notif_{uuid.uuid4().hex[:8]}")
    order_id = Column(String, nullable=True, index=True)
    client_id = Column(String, nullable=False, index=True)
    status = Column(
        SQLEnum(OrderStatus, name="orderstatus", values_callable=_enum_values),
        nullable=False,
    )
    channel = Column(
        SQLEnum(NotificationChannel, name="notificationchannel", values_callable=_enum_values),
        nullable=False,
    )
    message = Column(String, nullable=False)
    meta_data = Column("metadata", JSON, nullable=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    read_at = Column(DateTime(timezone=True), nullable=True)
    estimated_delivery_time = Column(DateTime(timezone=True), nullable=True)
    courier_name = Column(String, nullable=True)
    tracking_url = Column(String, nullable=True)


class PromoNotification(Base):
    __tablename__ = "promo_notifications"

    id = Column(String, primary_key=True, default=lambda: f"promo_{uuid.uuid4().hex[:8]}")
    title = Column(String(200), nullable=False)
    message = Column(String(1000), nullable=False)
    promo_code = Column(String, nullable=True)
    discount_percent = Column(Integer, nullable=True)
    image_url = Column(String, nullable=True)
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    target_audience = Column(
        SQLEnum(TargetAudience, name="targetaudience", values_callable=_enum_values),
        default=TargetAudience.ALL,
    )
    channels = Column(JSON, nullable=True)
    status = Column(
        SQLEnum(PromoStatus, name="promostatus", values_callable=_enum_values),
        default=PromoStatus.DRAFT,
    )
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    sent_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ClientSubscription(Base):
    __tablename__ = "client_subscriptions"

    client_id = Column(String, primary_key=True)

    order_sms = Column(Boolean, default=True)
    order_email = Column(Boolean, default=True)
    order_push = Column(Boolean, default=True)
    order_telegram = Column(Boolean, default=False)

    promo_sms = Column(Boolean, default=False)
    promo_email = Column(Boolean, default=True)
    promo_push = Column(Boolean, default=True)
    promo_telegram = Column(Boolean, default=False)

    quiet_hours_enabled = Column(Boolean, default=False)
    quiet_hours_start = Column(String, nullable=True)
    quiet_hours_end = Column(String, nullable=True)

    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ReportTaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ReportTask(Base):
    __tablename__ = "report_tasks"

    id = Column(String, primary_key=True)
    kind = Column(String, nullable=False)
    status = Column(
        SQLEnum(ReportTaskStatus, name="reporttaskstatus", values_callable=_enum_values),
        nullable=False,
        default=ReportTaskStatus.PENDING,
    )
    progress = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    result_file = Column(String, nullable=True)
    error_message = Column(String, nullable=True)


class DashboardView(Base):
    __tablename__ = "dashboard_views"

    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    user_id = Column(String, nullable=False, index=True)
    viewed_at = Column(DateTime(timezone=True), server_default=func.now())
