# Notification Service API

Микросервис управления уведомлениями для цветочного магазина.
Уведомления о статусах заказов и акционных предложениях.

## Возможности

- Отправка уведомлений об изменении статуса заказа
- Рассылка информации об акциях и сезонных предложениях
- Управление подписками на уведомления
- Статистика по уведомлениям

## Технологии

- FastAPI
- SQLAlchemy
- PostgreSQL
- Alembic (миграции БД)
- Docker & Docker Compose

## Установка и запуск

### Локальная разработка

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Создайте файл `.env` на основе `.env.example`:
```bash
cp .env.example .env
```

3. Настройте переменные окружения в `.env`:
```
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=notifications_db
DB_HOST=localhost
DB_PORT=5432
```

4. Убедитесь, что PostgreSQL запущен и создана база данных `notifications_db`.

5. Запустите миграции:
```bash
alembic upgrade head
```

6. Запустите приложение:
```bash
uvicorn app.main:app --reload
```

### Запуск через Docker Compose

1. Запустите все сервисы:
```bash
docker-compose up --build
```

Это автоматически:
- Запустит PostgreSQL
- Применит миграции БД
- Запустит FastAPI приложение

2. API будет доступно по адресу: http://localhost:8000
3. Документация API: http://localhost:8000/docs

## Миграции БД

### Создание новой миграции:
```bash
alembic revision --autogenerate -m "Описание изменений"
```

### Применение миграций:
```bash
alembic upgrade head
```

### Откат миграции:
```bash
alembic downgrade -1
```

## API Endpoints

- `GET /` - Информация о сервисе
- `GET /orders/{order_id}/notifications` - Получить уведомления по заказу
- `POST /orders/{order_id}/notifications` - Создать уведомление о заказе
- `GET /notifications/{notification_id}` - Получить уведомление по ID
- `POST /promo/notifications` - Создать акционное уведомление
- `GET /promo/notifications` - Список акционных уведомлений
- `GET /clients/{client_id}/subscriptions` - Получить подписки клиента
- `PUT /clients/{client_id}/subscriptions` - Обновить подписки клиента
- `GET /notifications/stats` - Статистика по уведомлениям

## Лаба: асинхронность и фоновые задачи

### Асинхронный CRUD

Все эндпоинты сервиса реализованы как `async def`, доступ к PostgreSQL выполнен через `SQLAlchemy AsyncSession` + драйвер `asyncpg`.

### Фоновая генерация отчёта с отслеживанием статуса

- `POST /reports/exports/notifications` — запускает долгую операцию “экспорт всех уведомлений в JSON”, сразу возвращает `task_id`
- `GET /reports/tasks/{task_id}` — проверка статуса/прогресса
- `GET /reports/tasks/{task_id}/result` — скачать результат (когда `status=completed`)

Результаты сохраняются в папку `generated_reports/` внутри контейнера (настраивается переменной окружения `REPORTS_DIR`).

### Комбинация: параллельный сбор + фоновое логирование

- `GET /dashboard/{user_id}` — параллельно собирает “profile/activity/recommendations” (через `asyncio.gather`)
- после ответа пишет лог просмотра в фоне (FastAPI `BackgroundTasks`) в `generated_reports/dashboard_views.log` и фиксирует просмотр в таблице `dashboard_views`

## Структура проекта

```
notification-service/
├── app/
│   ├── __init__.py
│   ├── main.py          # Основной файл приложения с эндпоинтами
│   ├── models.py        # SQLAlchemy модели
│   └── database.py      # Конфигурация БД
├── alembic/             # Миграции БД
│   ├── versions/
│   ├── env.py
│   └── script.py.mako
├── alembic.ini          # Конфигурация Alembic
├── docker-compose.yml   # Docker Compose конфигурация
├── dockerfile           # Docker образ приложения
├── requirements.txt     # Python зависимости
└── README.md
```

## Переменные окружения

- `DB_USER` - Пользователь БД (по умолчанию: postgres)
- `DB_PASSWORD` - Пароль БД (по умолчанию: postgres)
- `DB_NAME` - Имя БД (по умолчанию: notifications_db)
- `DB_HOST` - Хост БД (по умолчанию: localhost)
- `DB_PORT` - Порт БД (по умолчанию: 5432)

