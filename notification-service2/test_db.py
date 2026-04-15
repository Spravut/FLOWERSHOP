import asyncio
from app.database import engine
from sqlalchemy import text

async def test_connection():
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            print("✓ Подключение к БД успешно!")
            print(f"Результат: {result.scalar()}")
    except Exception as e:
        print(f"✗ Ошибка подключения: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())