# tests/test_notifications.py
"""
Интеграционные тесты для уведомлений (асинхронные).
"""
import pytest


@pytest.mark.asyncio
class TestOrderNotifications:
    """Тесты для уведомлений о заказах."""
    
    async def test_create_order_notification(self, client):
        """Создание уведомления о заказе."""
        order_id = "test-order-123"
        response = await client.post(
            f"/orders/{order_id}/notifications",
            json={
                "status": "confirmed",
                "channel": "sms"
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["order_id"] == order_id
        assert data["status"] == "confirmed"
        assert data["channel"] == "sms"
        assert "id" in data
    
    async def test_get_root_endpoint(self, client):
        """Проверка корневого эндпоинта."""
        response = await client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["version"] == "1.1.0"
    
    async def test_get_order_notifications(self, client):
        """Получение уведомлений по заказу."""
        order_id = "test-order-get"
        
        # Создаём уведомление
        await client.post(f"/orders/{order_id}/notifications",
                         json={"status": "confirmed", "channel": "sms"})
        
        # Получаем список
        response = await client.get(f"/orders/{order_id}/notifications")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
    
    async def test_get_single_notification(self, client):
        """Получение одного уведомления по ID."""
        # Создаём
        create_resp = await client.post("/orders/test-get-one/notifications",
                                       json={"status": "delivered", "channel": "sms"})
        notification_id = create_resp.json()["id"]
        
        # Получаем по ID
        response = await client.get(f"/notifications/{notification_id}")
        
        assert response.status_code == 200
        assert response.json()["id"] == notification_id
    
    async def test_get_nonexistent_notification(self, client):
        """Получение несуществующего уведомления."""
        response = await client.get("/notifications/nonexistent-id")
        assert response.status_code == 404
    
    async def test_update_notification(self, client):
        """Обновление уведомления."""
        # Создаём
        create_resp = await client.post("/orders/test-update/notifications",
                                       json={"status": "confirmed", "channel": "sms"})
        notification_id = create_resp.json()["id"]
        
        # Обновляем
        update_resp = await client.put(
            f"/notifications/{notification_id}",
            json={"status": "delivered", "read": True}
        )
        
        assert update_resp.status_code == 200
        assert update_resp.json()["status"] == "delivered"
    
    async def test_delete_notification(self, client):
        """Удаление уведомления."""
        # Создаём
        create_resp = await client.post("/orders/test-delete/notifications",
                                       json={"status": "confirmed", "channel": "sms"})
        notification_id = create_resp.json()["id"]
        
        # Удаляем
        delete_resp = await client.delete(f"/notifications/{notification_id}")
        assert delete_resp.status_code == 204
        
        # Проверяем, что удалилось
        get_resp = await client.get(f"/notifications/{notification_id}")
        assert get_resp.status_code == 404


@pytest.mark.asyncio
class TestNotificationStats:
    """Тесты для статистики уведомлений."""
    
    async def test_stats_get(self, client):
        """Получение статистики."""
        # Создаём тестовые данные
        for i in range(3):
            await client.post(
                f"/orders/stats-test-{i}/notifications",
                json={"status": "confirmed", "channel": "sms"}
            )
        
        response = await client.get("/notifications/stats?period=week")
        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "week"
        assert "total_sent" in data
        assert data["total_sent"] >= 0
    
    async def test_stats_different_periods(self, client):
        """Статистика за разные периоды."""
        for period in ["day", "week", "month"]:
            response = await client.get(f"/notifications/stats?period={period}")
            assert response.status_code == 200
            data = response.json()
            assert data["period"] == period
    
    async def test_stats_invalid_period(self, client):
        """Невалидный период - принимает любое значение."""
        response = await client.get("/notifications/stats?period=year")
        assert response.status_code == 200
        data = response.json()
        # Эндпоинт принимает любое значение period
        assert data["period"] == "year"
    
    async def test_stats_empty_database(self, client):
        """Статистика с пустой БД."""
        response = await client.get("/notifications/stats?period=week")
        assert response.status_code == 200
        data = response.json()
        assert data["total_sent"] == 0
        assert data["by_channel"]["sms"] == 0