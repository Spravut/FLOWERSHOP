# tests/test_routes.py
import pytest
from httpx import AsyncClient, ASGITransport
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app

@pytest.mark.asyncio
async def test_list_all_routes():
    """Вывод всех зарегистрированных маршрутов."""
    print("\n=== Все зарегистрированные маршруты ===")
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            print(f"{route.methods} {route.path}")
        elif hasattr(route, "path"):
            print(f"Route: {route.path}")
    
    # Проверяем, есть ли среди них /notifications/stats
    stats_routes = [r for r in app.routes if hasattr(r, "path") and "stats" in r.path]
    print(f"\n=== Маршруты со 'stats' ===")
    for route in stats_routes:
        print(f"{route.methods if hasattr(route, 'methods') else 'ANY'} {route.path}")

@pytest.mark.asyncio
async def test_stats_endpoint_with_fixture(client):
    """Прямой тест эндпоинта статистики с фикстурой."""
    # Сначала проверим корневой эндпоинт
    response = await client.get("/")
    assert response.status_code == 200
    
    # Теперь пробуем разные варианты пути к статистике
    paths_to_try = [
        "/notifications/stats",
        "/stats",
        "/notification/stats",
        "/api/notifications/stats",
        "/notifications/stats/",
    ]
    
    print("\n=== Проверка возможных путей к статистике ===")
    for path in paths_to_try:
        resp = await client.get(path)
        print(f"{path}: {resp.status_code}")
        if resp.status_code == 200:
            print(f"  Работает! Ответ: {resp.json()}")