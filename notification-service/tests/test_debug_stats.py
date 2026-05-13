# tests/test_debug_stats.py
import pytest
from httpx import AsyncClient, ASGITransport
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app
from app.database import get_db, Base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

@pytest.mark.asyncio
async def test_stats_endpoint_direct():
    """Прямая проверка эндпоинта статистики с минимальной настройкой."""
    
    # Создаём тестовую БД
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    # Создаём таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Подменяем зависимость get_db
    async def override_get_db():
        async with async_session_maker() as session:
            yield session
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Тестируем эндпоинт
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        print("\n=== Проверка корневого эндпоинта ===")
        response = await client.get("/")
        print(f"Status: {response.status_code}")
        
        print("\n=== Проверка /notifications/stats ===")
        response = await client.get("/notifications/stats?period=week")
        print(f"Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Response text: {response.text}")
        
        # Проверяем, зарегистрирован ли эндпоинт
        print("\n=== Проверка всех маршрутов ===")
        for route in app.routes:
            print(f"{route.methods} {route.path}")
    
    # Очищаем
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_stats_with_data():
    """Тест статистики с предварительно созданными данными."""
    
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async def override_get_db():
        async with async_session_maker() as session:
            yield session
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Создаём тестовые данные
    from app.models import Notification, NotificationChannel, OrderStatus
    from datetime import datetime, timedelta
    
    async with async_session_maker() as session:
        # Создаём несколько уведомлений
        for i in range(5):
            notification = Notification(
                id=f"test_notif_{i}",
                order_id=f"order_{i}",
                client_id=f"client_{i}",
                status=OrderStatus.CONFIRMED,
                channel=NotificationChannel.SMS,
                message=f"Test message {i}",
                sent_at=datetime.now() - timedelta(days=i)
            )
            session.add(notification)
        await session.commit()
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/notifications/stats?period=week")
        print(f"\nStatus with data: {response.status_code}")
        if response.status_code == 200:
            print(f"Response: {response.json()}")
    
    app.dependency_overrides.clear()