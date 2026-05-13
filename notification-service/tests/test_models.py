# tests/test_models.py
"""
Unit-тесты для Pydantic-моделей.
"""

import pytest
from datetime import datetime, timezone
from app.main import NotificationCreate, PromoNotificationCreate
from app.models import OrderStatus, NotificationChannel, TargetAudience


class TestNotificationCreate:
    """Тесты для модели создания уведомления."""
    
    def test_notification_create_valid(self):
        """Проверяем, что корректные данные проходят валидацию."""
        data = {
            "status": OrderStatus.OUT_FOR_DELIVERY,
            "channel": NotificationChannel.SMS,
        }
        notification = NotificationCreate(**data)
        
        assert notification.status == OrderStatus.OUT_FOR_DELIVERY
        assert notification.channel == NotificationChannel.SMS
    
    def test_notification_create_with_custom_message(self):
        """Проверяем создание с кастомным сообщением."""
        data = {
            "status": OrderStatus.CONFIRMED,
            "channel": NotificationChannel.EMAIL,
            "custom_message": "Моё сообщение"
        }
        notification = NotificationCreate(**data)
        
        assert notification.custom_message == "Моё сообщение"


class TestPromoNotificationCreate:
    """Тесты для модели создания акционного уведомления."""
    
    def test_promo_notification_create_valid(self):
        """Проверяем корректные данные."""
        now = datetime.now(timezone.utc)
        data = {
            "title": "Акция",
            "message": "Скидка 20%",
            "start_date": now.isoformat(),
            "end_date": now.isoformat(),
        }
        promo = PromoNotificationCreate(**data)
        
        assert promo.title == "Акция"
        assert promo.message == "Скидка 20%"
    
    def test_promo_notification_with_discount(self):
        """Проверяем создание со скидкой."""
        now = datetime.now(timezone.utc)
        data = {
            "title": "Скидка",
            "message": "50%",
            "discount_percent": 50,
            "start_date": now.isoformat(),
            "end_date": now.isoformat(),
        }
        promo = PromoNotificationCreate(**data)
        
        assert promo.discount_percent == 50