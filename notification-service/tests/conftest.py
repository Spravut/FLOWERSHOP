# tests/conftest.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db

# Асинхронная тестовая БД SQLite (in-memory)
SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Фабрика сессий
TestingSessionLocal = async_sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

@pytest.fixture(scope="function")
async def db_session():
    """Фикстура для тестовой БД."""
    # Создаём таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Создаём сессию
    async with TestingSessionLocal() as session:
        yield session
    
    # Очищаем после теста
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture(scope="function")
async def client(db_session):
    """Фикстура для клиента API."""
    
    # ВАЖНО: переопределяем get_db для каждого теста
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Создаём транспорт и клиента
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    
    # Очищаем после теста
    app.dependency_overrides.clear()