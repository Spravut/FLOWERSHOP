import asyncio
from datetime import datetime
from app.database import AsyncSessionLocal
from app.models import Notification, OrderStatus, NotificationChannel
from sqlalchemy import select, func

async def create_test_data():
    async with AsyncSessionLocal() as session:
        # Проверяем, есть ли данные
        count = await session.scalar(select(func.count()).select_from(Notification))
        
        if count == 0:
            # Создаём тестовые уведомления
            for i in range(5):
                notification = Notification(
                    id=f"test_notif_{i}",
                    order_id=f"order_{i}",
                    client_id=f"client_{i}",
                    status=OrderStatus.CONFIRMED,
                    channel=NotificationChannel.EMAIL,
                    message=f"Тестовое уведомление {i}",
                    sent_at=datetime.now()
                )
                session.add(notification)
            
            await session.commit()
            print(f"✓ Создано 5 тестовых уведомлений")
        else:
            print(f"✓ В базе уже есть {count} уведомлений")

if __name__ == "__main__":
    asyncio.run(create_test_data())