# 🌸 Fleur de Rêve — Docker Flowershop

Монолитное Django-приложение интернет-магазина цветов с двумя микросервисами на FastAPI:

| Сервис | Технология | Способ связи | Порт |
|--------|-----------|-------------|------|
| **Django Monolith** (flowershop) | Django 5.0 | — | `8002` |
| **Reviews Service** (docker-practice) | FastAPI | **HTTP REST** | `8000` |
| **Notification Service** (notification-service) | FastAPI | **NATS JetStream** (брокер сообщений) | `8001` |

---

## 📁 Структура проекта

```
docker-flowershop/
├── docker-compose.yml              # Главный compose — поднимает ВСЁ
├── flowershop/                     # Django-монолит
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── manage.py
│   ├── flowershop/                 # Настройки Django-проекта
│   │   ├── settings.py             # NATS_URL, REVIEWS_SERVICE_URL
│   │   ├── urls.py
│   │   └── ...
│   └── main/                       # Основное Django-приложение
│       ├── views.py                # Вьюхи (reviews → HTTP к микросервису)
│       ├── reviews_client.py       # HTTP-клиент к Reviews Service
│       ├── nats_events.py          # Публикация событий в NATS
│       ├── signals.py              # Django signals → NATS при создании/изменении заказа
│       ├── models.py               # Order, Product, Cart, Review, ...
│       ├── apps.py                 # Подключение signals в ready()
│       └── templates/main/         # HTML-шаблоны
│
├── docker-practice/                # Микросервис отзывов (Reviews)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic/                    # Миграции БД
│   └── app/
│       ├── main.py                 # FastAPI-приложение с эндпоинтами
│       ├── models.py               # SQLAlchemy-модели
│       ├── schemas.py              # Pydantic-схемы
│       ├── crud.py                 # CRUD-операции
│       ├── database.py             # Подключение к PostgreSQL
│       └── review_validation.py    # Автопроверка отзывов
│
└── notification-service/          # Микросервис уведомлений (Notification)
    ├── dockerfile
    ├── requirements.txt
    ├── alembic/                    # Миграции БД
    └── app/
        ├── main.py                 # FastAPI + lifespan (запуск NATS consumer)
        ├── models.py               # SQLAlchemy-модели
        ├── database.py             # Async подключение к PostgreSQL
        └── nats_consumer.py        # NATS JetStream consumer
```

---

## 🚀 Быстрый старт

```bash
# Клонировать репозиторий
git clone <repo-url>
cd docker-flowershop

# Запустить все сервисы
docker compose up -d --build

# Проверить статус
docker compose ps
```

После запуска:
- **Django (магазин):** http://localhost:8002
- **Reviews API (Swagger):** http://localhost:8000/docs
- **Notification API (Swagger):** http://localhost:8001/docs
- **NATS Monitoring:** http://localhost:8222

---

## 🔗 Подключение микросервиса отзывов через HTTP (Reviews Service)

### Общая схема

```
┌──────────────┐    HTTP GET/POST     ┌──────────────────┐     SQL      ┌──────────────┐
│    Django     │ ──────────────────→  │  Reviews Service  │ ──────────→ │  reviews-db   │
│  (flowershop) │ ←────────────────── │  (FastAPI :8000)  │ ←────────── │ (PostgreSQL)  │
└──────────────┘    JSON response     └──────────────────┘             └──────────────┘
```

Django общается с Reviews Service **напрямую по HTTP** — классический REST-подход. Никакого брокера сообщений, никакой очереди. Просто `requests.get()` / `requests.post()`.

### Где задаётся URL микросервиса

**Файл:** [`flowershop/flowershop/settings.py`](flowershop/flowershop/settings.py:145)

```python
# Reviews микросервис (в Docker: reviews-service)
REVIEWS_SERVICE_URL = os.environ.get('REVIEWS_SERVICE_URL', 'http://localhost:8000')
```

В Docker Compose переменная окружения задаётся так:

**Файл:** [`docker-compose.yml`](docker-compose.yml:31)

```yaml
django:
  environment:
    - REVIEWS_SERVICE_URL=http://reviews-service:8000
```

`reviews-service` — это имя сервиса в Docker Compose. Docker автоматически резолвит его в IP-адрес контейнера.

### HTTP-клиент (reviews_client.py)

**Файл:** [`flowershop/main/reviews_client.py`](flowershop/main/reviews_client.py:1)

Это модуль-обёртка, который инкапсулирует все HTTP-запросы к микросервису отзывов. Содержит три функции:

#### 1. `fetch_reviews()` — получение списка отзывов

```python
def fetch_reviews(approved_only=True, limit=50, offset=0):
    resp = requests.get(
        f'{BASE_URL}/reviews',
        params={'approved_only': approved_only, 'limit': limit, 'offset': offset},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    items = [ReviewDisplay(r) for r in data.get('items', [])]
    total = data.get('total', len(items))
    return items, total
```

- Отправляет `GET /reviews` на микросервис
- Получает JSON с полями `items` (массив отзывов) и `total` (общее количество)
- Оборачивает каждый отзыв в класс `ReviewDisplay` для удобного отображения в Django-шаблонах
- При ошибке соединения возвращает пустой список `([], 0)` — страница не падает

#### 2. `fetch_rating_summary()` — сводка рейтинга

```python
def fetch_rating_summary(approved_only=True, product_id=None):
    resp = requests.get(f'{BASE_URL}/ratings/summary', params=params, timeout=TIMEOUT)
    data = resp.json()
    return data.get('average'), data.get('count', 0)
```

- Отправляет `GET /ratings/summary`
- Возвращает средний рейтинг и количество отзывов

#### 3. `create_review()` — создание отзыва

```python
def create_review(name, text, rating=5, product_id=None, user_id=None):
    resp = requests.post(f'{BASE_URL}/reviews', json=payload, timeout=TIMEOUT)
    if resp.status_code == 201:
        return resp.json(), None
    if resp.status_code == 422:
        # Отзыв не прошёл автопроверку
        return None, msg
```

- Отправляет `POST /reviews` с JSON-телом
- При `201 Created` — отзыв создан успешно
- При `422 Unprocessable Entity` — отзыв не прошёл автоматическую проверку (спам, ссылки, мат)
- При сетевой ошибке — возвращает сообщение «Сервис временно недоступен»

### Класс ReviewDisplay

```python
class ReviewDisplay:
    def __init__(self, data: dict):
        self.id = data.get('id')
        self.name = data.get('name', '')
        self.text = data.get('text', '')
        self.rating = int(data.get('rating', 5))
        self.is_approved = data.get('is_approved', False)
        self.created_at = ...  # парсинг ISO даты
```

Этот класс нужен, чтобы данные из JSON-ответа микросервиса выглядели как Django-модель в шаблонах. Шаблон `reviews.html` обращается к `review.name`, `review.text`, `review.rating` — и ему всё равно, откуда пришли данные.

### Как вызывается из Django view

**Файл:** [`flowershop/main/views.py`](flowershop/main/views.py:134) — функция `reviews()`

```python
def reviews(request):
    from .reviews_client import create_review, fetch_rating_summary, fetch_reviews

    # POST — создание отзыва
    if request.method == 'POST':
        result, err = create_review(name=name, text=text, rating=rating, ...)
        if result:
            messages.success(request, 'Спасибо за отзыв!')
        elif err:
            messages.error(request, err)
        return redirect('reviews')

    # GET — получение отзывов
    reviews_list, total_reviews = fetch_reviews(approved_only=True, limit=50)
    avg_rating_val, count = fetch_rating_summary(approved_only=True)
    ...
    return render(request, 'main/reviews.html', context)
```

### URL-маршрут

**Файл:** [`flowershop/main/urls.py`](flowershop/main/urls.py:10)

```python
path('reviews/', views.reviews, name='reviews'),
```

Пользователь заходит на `http://localhost:8002/reviews/` → Django вызывает `views.reviews()` → тот делает HTTP-запрос к `http://reviews-service:8000/reviews` → получает JSON → рендерит HTML.

### Что происходит на стороне микросервиса

**Файл:** [`docker-practice/app/main.py`](docker-practice/app/main.py:141)

```python
@app.get("/reviews", response_model=schemas.ReviewList)
def read_reviews(limit, offset, approved_only, product_id, min_rating, max_rating, sort, db):
    items, total = crud.get_reviews(db, ...)
    return schemas.ReviewList(items=items, total=total)

@app.post("/reviews", response_model=schemas.ReviewResponse, status_code=201)
def create_review(review, db):
    error_msg = validate_review_text(name=review.name, text=review.text)
    if error_msg:
        raise HTTPException(status_code=422, detail=error_msg)
    return crud.create_review(db, review, is_approved=True)
```

Микросервис:
1. Принимает HTTP-запрос
2. Валидирует данные (Pydantic-схемы)
3. Проверяет текст на спам/мат (`review_validation.py`)
4. Сохраняет в свою PostgreSQL (`reviews-db`)
5. Возвращает JSON-ответ

### Полная цепочка (пример: пользователь оставляет отзыв)

```
1. Пользователь заполняет форму на /reviews/ и нажимает "Отправить"
2. Браузер отправляет POST на Django (localhost:8002/reviews/)
3. Django view reviews() получает POST-данные из request.POST
4. reviews_client.create_review() отправляет POST http://reviews-service:8000/reviews
   с JSON: {"name": "Иван", "text": "Отличные цветы!", "rating": 5}
5. FastAPI микросервис:
   a. Валидирует JSON через Pydantic
   b. Проверяет текст на спам (review_validation.py)
   c. Сохраняет в PostgreSQL (reviews-db)
   d. Возвращает 201 + JSON с созданным отзывом
6. Django получает ответ, показывает flash-сообщение "Спасибо за отзыв!"
7. Redirect на GET /reviews/
8. Django вызывает fetch_reviews() → GET http://reviews-service:8000/reviews
9. Микросервис возвращает список отзывов из БД
10. Django рендерит HTML-шаблон reviews.html с данными
```

---

## 📨 Подключение микросервиса уведомлений через NATS JetStream (Notification Service)

### Общая схема

```
┌──────────────┐   publish (async)   ┌───────────┐   subscribe    ┌─────────────────────┐    SQL     ┌─────────────────┐
│    Django     │ ─────────────────→  │   NATS    │ ─────────────→ │ Notification Service │ ────────→ │ notification-db  │
│  (flowershop) │                     │ JetStream │                │   (FastAPI :8001)    │ ←──────── │  (PostgreSQL)    │
└──────────────┘                     └───────────┘                └─────────────────────┘           └─────────────────┘
     │                                    ↑
     │  Django signals                    │
     │  (post_save Order)                 │
     └────────────────────────────────────┘
```

В отличие от Reviews Service, здесь Django **НЕ** делает HTTP-запросы к Notification Service. Вместо этого используется **брокер сообщений NATS JetStream**:

- **Django** — **publisher** (публикует события в NATS)
- **Notification Service** — **consumer** (подписывается на события и обрабатывает их)

Это **асинхронная** связь: Django отправляет сообщение и **не ждёт ответа**. Notification Service обработает его когда сможет.

### Зачем брокер сообщений?

1. **Развязка (decoupling):** Django не знает о Notification Service. Он просто публикует событие «заказ создан» в NATS. Кто его обработает — не его забота.
2. **Надёжность:** NATS JetStream гарантирует доставку. Если Notification Service упал — сообщения сохранятся в stream и будут обработаны после перезапуска.
3. **Асинхронность:** Django не блокируется, ожидая ответа. Пользователь сразу видит «Заказ оформлен!», а уведомление создаётся в фоне.

### Компоненты интеграции

#### 1. NATS Server (брокер)

**Файл:** [`docker-compose.yml`](docker-compose.yml:6)

```yaml
nats:
  image: nats:2.10-alpine
  command: ["-js", "-m", "8222"]
  ports:
    - "4222:4222"   # Клиентские подключения
    - "8222:8222"   # HTTP мониторинг
```

- `-js` — включает JetStream (persistent messaging)
- `-m 8222` — включает HTTP мониторинг
- Порт `4222` — основной порт для клиентов (Django и Notification Service подключаются сюда)

#### 2. Django: настройка NATS URL

**Файл:** [`flowershop/flowershop/settings.py`](flowershop/flowershop/settings.py:142)

```python
NATS_URL = os.environ.get('NATS_URL', 'nats://localhost:4222')
```

В Docker Compose:

```yaml
django:
  environment:
    - NATS_URL=nats://nats:4222
```

#### 3. Django: публикация событий (nats_events.py)

**Файл:** [`flowershop/main/nats_events.py`](flowershop/main/nats_events.py:1)

Этот модуль отвечает за **отправку сообщений в NATS** из Django.

##### Константы

```python
SUBJECT_ORDER_CREATED = "flowershop.orders.created"
SUBJECT_ORDER_STATUS_CHANGED = "flowershop.orders.status_changed"
STREAM_NAME = "FLOWERSHOP"
```

- **Subject** — это «тема» сообщения (аналог topic в Kafka). Notification Service подписывается на `flowershop.orders.>` (wildcard — все сообщения, начинающиеся с `flowershop.orders.`)
- **Stream** — это хранилище сообщений в JetStream. Сообщения сохраняются на диске и не теряются.

##### Запуск async кода из sync Django

```python
def _run_async(coro):
    """Запуск async кода из sync контекста (Django) в отдельном потоке."""
    def _run():
        try:
            asyncio.run(coro)
        except Exception as e:
            logger.exception("NATS publish error: %s", e)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
```

Django — синхронный фреймворк, а `nats-py` — асинхронная библиотека. Поэтому для публикации создаётся **отдельный поток** с собственным event loop. Поток — daemon, чтобы не блокировать завершение Django.

##### Подключение и публикация

```python
async def _ensure_stream_and_publish(subject, payload):
    nc = await nats.connect(settings.NATS_URL)
    js = nc.jetstream()

    # Создаём stream если не существует (idempotent)
    try:
        await js.add_stream(name=STREAM_NAME, subjects=["flowershop.orders.>"])
    except Exception:
        pass  # Stream уже существует

    data = json.dumps(payload, ensure_ascii=False).encode()
    await js.publish(subject, data)
    await nc.close()
```

1. Подключается к NATS
2. Получает JetStream context
3. Создаёт stream `FLOWERSHOP` (если ещё нет) с паттерном subjects `flowershop.orders.>`
4. Публикует JSON-сообщение в указанный subject
5. Закрывает соединение

##### Функции публикации

```python
def publish_order_created(order):
    payload = {
        "event": "order.created",
        "order_id": str(order.id),
        "customer_name": order.customer_name,
        "email": order.email,
        "phone": order.phone,
        "total_price": str(order.total_price),
        "status": order.status,
        "user_id": str(order.user_id) if order.user_id else None,
    }
    _run_async(_ensure_stream_and_publish(SUBJECT_ORDER_CREATED, payload))
```

```python
def publish_order_status_changed(order, old_status):
    status_map = {
        "new": "confirmed",
        "processing": "gathering",
        "delivering": "out_for_delivery",
        "completed": "delivered",
        "cancelled": "cancelled",
    }
    notification_status = status_map.get(order.status, order.status)

    payload = {
        "event": "order.status_changed",
        "order_id": str(order.id),
        "old_status": old_status,
        "new_status": order.status,
        "notification_status": notification_status,
        ...
    }
    _run_async(_ensure_stream_and_publish(SUBJECT_ORDER_STATUS_CHANGED, payload))
```

Обратите внимание на `status_map` — Django использует свои статусы (`new`, `processing`, `delivering`), а Notification Service — свои (`confirmed`, `gathering`, `out_for_delivery`). Маппинг происходит здесь.

#### 4. Django: автоматическая публикация через signals

**Файл:** [`flowershop/main/signals.py`](flowershop/main/signals.py:1)

```python
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Order
from .nats_events import publish_order_created, publish_order_status_changed

@receiver(post_save, sender=Order)
def order_post_save(sender, instance, created, **kwargs):
    if created:
        publish_order_created(instance)
    else:
        if instance.tracker.has_changed("status"):
            old_status = instance.tracker.previous("status")
            publish_order_status_changed(instance, old_status)
```

Django signals — это механизм «подписки на события» внутри Django. `post_save` срабатывает **после** сохранения модели в БД.

- Если заказ **создан** (`created=True`) → публикуем `order.created`
- Если заказ **обновлён** и **статус изменился** → публикуем `order.status_changed`

`instance.tracker` — это `FieldTracker` из `django-model-utils`, который отслеживает изменения полей модели.

**Файл:** [`flowershop/main/models.py`](flowershop/main/models.py:90)

```python
class Order(models.Model):
    ...
    tracker = FieldTracker(fields=["status"])
```

#### 5. Django: подключение signals при старте

**Файл:** [`flowershop/main/apps.py`](flowershop/main/apps.py:1)

```python
class MainConfig(AppConfig):
    name = 'main'

    def ready(self):
        import main.signals  # noqa: F401
```

Метод `ready()` вызывается при старте Django. Импорт `main.signals` регистрирует декоратор `@receiver`, и с этого момента все `post_save` на `Order` будут вызывать `order_post_save`.

#### 6. Notification Service: NATS consumer

**Файл:** [`notification-service/app/nats_consumer.py`](notification-service/app/nats_consumer.py:1)

Этот модуль — **подписчик** (consumer). Он работает в фоне и слушает сообщения из NATS.

##### Маппинг статусов

```python
STATUS_MAP = {
    "new": OrderStatus.CONFIRMED,
    "confirmed": OrderStatus.CONFIRMED,
    "processing": OrderStatus.GATHERING,
    "gathering": OrderStatus.GATHERING,
    "delivering": OrderStatus.OUT_FOR_DELIVERY,
    "out_for_delivery": OrderStatus.OUT_FOR_DELIVERY,
    "completed": OrderStatus.DELIVERED,
    "delivered": OrderStatus.DELIVERED,
    "cancelled": OrderStatus.CANCELLED,
}
```

Принимает статусы как от Django (`new`, `processing`), так и уже замапленные (`confirmed`, `gathering`).

##### Обработка события

```python
async def _handle_order_event(payload):
    order_id = payload.get("order_id")
    user_id = payload.get("user_id")
    email = payload.get("email", "")
    client_id = f"user_{user_id}" if user_id else f"email_{email}"

    notification_status_str = payload.get("notification_status") or payload.get("status")
    order_status = STATUS_MAP.get(str(notification_status_str).lower(), OrderStatus.CONFIRMED)

    message = _status_message(order_id, order_status)
    notification_id = f"notif_{uuid.uuid4().hex[:8]}"

    async with sessionmaker() as session:
        notification = Notification(
            id=notification_id,
            order_id=str(order_id),
            client_id=client_id,
            status=order_status,
            channel=NotificationChannel.EMAIL,
            message=message,
        )
        session.add(notification)
        await session.commit()
```

1. Извлекает данные из JSON-payload
2. Определяет `client_id` (по `user_id` или `email`)
3. Маппит статус Django → статус Notification Service
4. Генерирует текст уведомления с эмодзи
5. Сохраняет уведомление в PostgreSQL (`notification-db`)

##### Основной цикл consumer

```python
async def run_nats_consumer():
    while True:
        try:
            nc = await nats.connect(NATS_URL)
            js = nc.jetstream()

            # Создаём stream
            await js.add_stream(name=STREAM_NAME, subjects=["flowershop.orders.>"])

            # Pull-based consumer с durable подпиской
            psub = await js.pull_subscribe(
                SUBJECT_ORDERS,           # "flowershop.orders.>"
                durable=CONSUMER_NAME,    # "notification-service"
                stream=STREAM_NAME,       # "FLOWERSHOP"
            )

            while True:
                msgs = await psub.fetch(batch=5, timeout=5.0)
                for msg in msgs:
                    payload = json.loads(msg.data.decode())
                    await _handle_order_event(payload)
                    await msg.ack()  # Подтверждаем обработку

        except Exception:
            await asyncio.sleep(10)  # Переподключение через 10 сек
```

- **Pull-based consumer** — сам запрашивает сообщения пачками по 5 штук
- **Durable** — NATS запоминает, какие сообщения уже обработаны. При перезапуске consumer продолжит с того места, где остановился
- **ACK/NAK** — после успешной обработки отправляется `ack()`. При ошибке — `nak()` (сообщение будет переотправлено)
- **Автопереподключение** — при потере связи с NATS ждёт 10 секунд и пробует снова

#### 7. Notification Service: запуск consumer при старте

**Файл:** [`notification-service/app/main.py`](notification-service/app/main.py:44)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Запуск NATS JetStream consumer при старте приложения."""
    consumer_task = asyncio.create_task(run_nats_consumer())
    yield
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass

app = FastAPI(..., lifespan=lifespan)
```

`lifespan` — это механизм FastAPI для выполнения кода при старте и остановке приложения:
- **При старте:** создаёт asyncio task с NATS consumer (работает в фоне параллельно с HTTP-сервером)
- **При остановке:** отменяет task

### Полная цепочка (пример: пользователь оформляет заказ)

```
1. Пользователь нажимает "Оформить заказ" на /checkout/
2. Django view checkout() создаёт Order в SQLite:
   Order.objects.create(customer_name="Иван", email="ivan@mail.ru", ...)
3. Django signal post_save срабатывает (signals.py):
   order_post_save(sender=Order, instance=order, created=True)
4. Вызывается publish_order_created(order) (nats_events.py)
5. В отдельном потоке:
   a. Подключение к NATS (nats://nats:4222)
   b. Создание stream FLOWERSHOP (если нет)
   c. Публикация JSON в subject "flowershop.orders.created":
      {
        "event": "order.created",
        "order_id": "42",
        "customer_name": "Иван",
        "email": "ivan@mail.ru",
        "total_price": "2500.00",
        "status": "new"
      }
6. Django возвращает пользователю "Заказ оформлен!" (НЕ ждёт Notification Service)

--- Асинхронно, в Notification Service ---

7. NATS consumer (nats_consumer.py) получает сообщение из stream
8. _handle_order_event() парсит JSON
9. Маппит статус: "new" → OrderStatus.CONFIRMED
10. Генерирует текст: "✅ Заказ №42 подтверждён! Начинаем собирать букет."
11. Сохраняет Notification в PostgreSQL (notification-db)
12. Отправляет ack() в NATS (сообщение обработано)
```

### Что происходит при смене статуса заказа

```
1. Админ меняет статус заказа в Django Admin: "new" → "processing"
2. Order.save() → post_save signal
3. instance.tracker.has_changed("status") → True
4. publish_order_status_changed(order, old_status="new")
5. Маппинг: "processing" → "gathering"
6. Публикация в NATS subject "flowershop.orders.status_changed":
   {
     "event": "order.status_changed",
     "order_id": "42",
     "old_status": "new",
     "new_status": "processing",
     "notification_status": "gathering"
   }
7. Notification Service создаёт уведомление:
   "👩‍🌾 Флорист собирает ваш букет для заказа №42"
```

---

## 🔄 Сравнение двух подходов

| Характеристика | HTTP (Reviews) | NATS JetStream (Notifications) |
|---|---|---|
| **Тип связи** | Синхронная | Асинхронная |
| **Django ждёт ответ?** | Да | Нет |
| **Что если микросервис упал?** | Ошибка на странице (graceful) | Сообщения копятся в NATS, обработаются позже |
| **Направление** | Django → Микросервис → Django | Django → NATS → Микросервис |
| **Гарантия доставки** | Нет (retry на уровне кода) | Да (JetStream persistent) |
| **Подходит для** | Запрос-ответ (CRUD) | События, уведомления, fire-and-forget |
| **Библиотека** | `requests` | `nats-py` |

---

## 🐳 Docker Compose: сервисы и зависимости

```
                    ┌─────────┐
                    │  NATS   │
                    │ :4222   │
                    └────┬────┘
                         │
              ┌──────────┼──────────┐
              │          │          │
              ▼          ▼          │
        ┌──────────┐  ┌──────────────────┐
        │  Django   │  │  Notification    │
        │  :8002    │  │  Service :8001   │
        └────┬─────┘  └───────┬──────────┘
             │                │
             │          ┌─────▼──────┐
             │          │notification│
             │          │   -db      │
             │          │  :5433     │
             │          └────────────┘
             │
       ┌─────▼──────┐
       │  Reviews    │
       │  Service    │
       │  :8000      │
       └─────┬───────┘
             │
       ┌─────▼──────┐
       │ reviews-db  │
       │  :5432      │
       └─────────────┘
```

### Порты

| Сервис | Внутренний порт | Внешний порт | URL |
|--------|----------------|-------------|-----|
| Django | 8000 | **8002** | http://localhost:8002 |
| Reviews Service | 8000 | **8000** | http://localhost:8000 |
| Notification Service | 8000 | **8001** | http://localhost:8001 |
| NATS | 4222 | **4222** | nats://localhost:4222 |
| NATS Monitoring | 8222 | **8222** | http://localhost:8222 |
| Reviews DB (PostgreSQL) | 5432 | **5432** | localhost:5432 |
| Notification DB (PostgreSQL) | 5432 | **5433** | localhost:5433 |

### Зависимости запуска

```yaml
django:
  depends_on:
    nats: service_healthy          # Ждёт пока NATS будет готов
    reviews-service: service_started  # Ждёт пока Reviews запустится

notification-service:
  depends_on:
    notification-db: service_healthy  # Ждёт пока PostgreSQL будет готов
    nats: service_healthy             # Ждёт пока NATS будет готов

reviews-service:
  depends_on:
    reviews-db: service_healthy       # Ждёт пока PostgreSQL будет готов
```

---

## 🛠 Полезные команды

```bash
# Запуск всех сервисов
docker compose up -d --build

# Просмотр логов
docker compose logs -f django
docker compose logs -f notification-service
docker compose logs -f reviews-service
docker compose logs -f nats

# Перезапуск одного сервиса
docker compose restart notification-service

# Остановка всех сервисов
docker compose down

# Остановка + удаление данных (volumes)
docker compose down -v

# Проверка NATS streams
docker exec flowershop_nats nats stream ls
docker exec flowershop_nats nats stream info FLOWERSHOP

# Проверка NATS consumers
docker exec flowershop_nats nats consumer ls FLOWERSHOP
```

---

## 📝 Переменные окружения

### Django

| Переменная | Значение | Описание |
|-----------|---------|---------|
| `DEBUG` | `1` | Режим отладки |
| `NATS_URL` | `nats://nats:4222` | URL NATS-сервера |
| `REVIEWS_SERVICE_URL` | `http://reviews-service:8000` | URL микросервиса отзывов |

### Notification Service

| Переменная | Значение | Описание |
|-----------|---------|---------|
| `DB_USER` | `postgres` | Пользователь PostgreSQL |
| `DB_PASSWORD` | `postgres` | Пароль PostgreSQL |
| `DB_NAME` | `notifications_db` | Имя базы данных |
| `DB_HOST` | `notification-db` | Хост PostgreSQL (имя сервиса в Docker) |
| `DB_PORT` | `5432` | Порт PostgreSQL (внутренний) |
| `NATS_URL` | `nats://nats:4222` | URL NATS-сервера |

### Reviews Service

| Переменная | Значение | Описание |
|-----------|---------|---------|
| `DB_USER` | `postgres` | Пользователь PostgreSQL |
| `DB_PASSWORD` | `postgres` | Пароль PostgreSQL |
| `DB_NAME` | `reviews_db` | Имя базы данных |
| `DB_HOST` | `reviews-db` | Хост PostgreSQL |
| `DB_PORT` | `5432` | Порт PostgreSQL |
