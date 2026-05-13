# Подключение микросервисов к монолиту: полный разбор

Документ описывает **оба** способа интеграции микросервисов с Django-монолитом:

1. **Reviews Service** — подключён по **HTTP** (синхронные запросы `requests`).
2. **Notification Service** — подключён через **NATS JetStream** (асинхронный брокер сообщений).

---

## 1. Общая архитектура

```
┌──────────────────────────────────────────────────────────────────┐
│                        Docker Compose                            │
│                                                                  │
│  ┌──────────┐   HTTP (requests)   ┌─────────────────────┐       │
│  │  Django   │ ──────────────────► │  Reviews Service    │       │
│  │ (монолит) │                     │  (FastAPI + PG)     │       │
│  │ :8002     │                     │  :8000              │       │
│  └────┬──────┘                     └─────────────────────┘       │
│       │                                                          │
│       │  publish (NATS JetStream)                                │
│       ▼                                                          │
│  ┌──────────┐                      ┌─────────────────────┐       │
│  │   NATS   │ ◄─── pull subscribe  │ Notification Service│       │
│  │  :4222   │ ────────────────────► │  (FastAPI + PG)     │       │
│  └──────────┘                      │  :8001              │       │
│                                    └─────────────────────┘       │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Инфраструктура: docker-compose.yml

| Сервис | Образ / контекст | Порт (хост → контейнер) | Роль |
|--------|-----------------|------------------------|------|
| `nats` | `nats:2.10-alpine` | 4222:4222, 8222:8222 | Брокер сообщений с JetStream (`-js`), мониторинг (`-m 8222`) |
| `django` | `./flowershop` | 8002:8000 | Монолит Django |
| `reviews-service` | `./docker-practice` | 8000:8000 | Микросервис отзывов (FastAPI + PostgreSQL) |
| `reviews-db` | `postgres:15` | 5432:5432 | БД для отзывов |
| `notification-service` | `./notification-service` | 8001:8000 | Микросервис уведомлений (FastAPI + PostgreSQL) |
| `notification-db` | `postgres:15-alpine` | 5433:5432 | БД для уведомлений |

Переменные окружения Django:

```yaml
environment:
  - NATS_URL=nats://nats:4222
  - REVIEWS_SERVICE_URL=http://reviews-service:8000
```

Настройки в `flowershop/flowershop/settings.py`:

```python
NATS_URL = os.environ.get('NATS_URL', 'nats://localhost:4222')
REVIEWS_SERVICE_URL = os.environ.get('REVIEWS_SERVICE_URL', 'http://localhost:8000')
```

---

# Часть I. Reviews Service — подключение по HTTP

---

## 3. Зачем HTTP для отзывов

Отзывы — это **запрос-ответ**: пользователь отправляет отзыв и сразу видит результат (создан / ошибка валидации). Страница отзывов загружает список из микросервиса и показывает его. Здесь нужна **синхронная** связь, поэтому используется обычный HTTP.

---

## 4. Reviews Service API (FastAPI)

Микросервис живёт в `docker-practice/`, точка входа — `app/main.py`.

Основные эндпоинты:

| Метод | URL | Описание |
|-------|-----|----------|
| `GET` | `/reviews` | Список отзывов (фильтры: `approved_only`, `product_id`, `min_rating`, `max_rating`, `sort`, пагинация) |
| `POST` | `/reviews` | Создать отзыв (с автоматической валидацией текста) |
| `GET` | `/reviews/{reviewId}` | Получить один отзыв |
| `PATCH` | `/reviews/{reviewId}` | Обновить отзыв |
| `DELETE` | `/reviews/{reviewId}` | Удалить отзыв |
| `GET` | `/ratings/summary` | Средний рейтинг и количество отзывов |

При создании отзыва (`POST /reviews`) срабатывает автоматическая валидация (`review_validation.py`): проверка на ссылки, спам, ненормативную лексику. Если текст не прошёл — возвращается `422`.

---

## 5. HTTP-клиент в Django: `reviews_client.py`

Файл `flowershop/main/reviews_client.py` — обёртка над `requests` для вызова Reviews Service.

### 5.1. Константы

```python
BASE_URL = getattr(settings, 'REVIEWS_SERVICE_URL', 'http://localhost:8000')
TIMEOUT = 10
```

`BASE_URL` берётся из `settings.REVIEWS_SERVICE_URL`. В Docker это `http://reviews-service:8000` (DNS-имя контейнера).

### 5.2. Класс `ReviewDisplay`

Преобразует JSON-ответ микросервиса в объект, удобный для шаблонов Django:

- `id`, `name`, `text`, `rating`, `is_approved`, `created_at`
- Метод `get_stars()` → строка вида `★★★★☆`

### 5.3. Функция `fetch_reviews()`

```python
def fetch_reviews(approved_only=True, limit=50, offset=0) -> tuple[list, int]:
```

1. `GET {BASE_URL}/reviews` с параметрами `approved_only`, `limit`, `offset`.
2. Парсит JSON: `items` → список `ReviewDisplay`, `total` → общее количество.
3. При ошибке (`RequestException`) — возвращает пустой список, логирует предупреждение.

### 5.4. Функция `fetch_rating_summary()`

```python
def fetch_rating_summary(approved_only=True, product_id=None) -> tuple[Optional[float], int]:
```

1. `GET {BASE_URL}/ratings/summary`.
2. Возвращает `(average, count)`.
3. При ошибке — `(None, 0)`.

### 5.5. Функция `create_review()`

```python
def create_review(name, text, rating=5, product_id=None, user_id=None) -> Tuple[Optional[dict], Optional[str]]:
```

1. `POST {BASE_URL}/reviews` с JSON-телом `{name, text, rating, product_id, user_id}`.
2. `201` → `(response_json, None)` — успех.
3. `422` → `(None, error_message)` — отзыв не прошёл валидацию.
4. `RequestException` → `(None, "Сервис отзывов временно недоступен...")`.

### 5.6. Обработка ошибок

Все функции оборачивают вызовы в `try/except requests.RequestException`. Если Reviews Service недоступен, Django **не падает** — просто показывает пустую страницу отзывов или сообщение об ошибке.

---

## 6. Использование в Django views

Файл `flowershop/main/views.py`, функция `reviews()`:

```python
def reviews(request):
    from .reviews_client import create_review, fetch_rating_summary, fetch_reviews

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        text = request.POST.get('text', '').strip()
        rating = int(request.POST.get('rating', 5))

        if name and text:
            result, err = create_review(
                name=name, text=text, rating=rating,
                user_id=request.user.id if request.user.is_authenticated else None,
            )
            if result:
                messages.success(request, 'Спасибо за отзыв!')
            elif err:
                messages.error(request, err)

        return redirect('reviews')

    reviews_list, total_reviews = fetch_reviews(approved_only=True, limit=50)
    avg_rating_val, count = fetch_rating_summary(approved_only=True)
    ...
    return render(request, 'main/reviews.html', context)
```

**Поток данных:**

1. Пользователь открывает `/reviews/` → Django вызывает `fetch_reviews()` и `fetch_rating_summary()` → HTTP GET к Reviews Service → JSON → рендер шаблона.
2. Пользователь отправляет форму → Django вызывает `create_review()` → HTTP POST к Reviews Service → результат/ошибка → redirect.

---

## 7. Зависимости в docker-compose

```yaml
django:
  depends_on:
    reviews-service:
      condition: service_started
```

Django стартует **после** Reviews Service. Но даже если сервис упадёт позже, Django продолжит работать — просто отзывы будут недоступны (graceful degradation).

---

# Часть II. Notification Service — подключение через NATS JetStream

---

## 8. Зачем брокер сообщений

**Проблема без брокера:** Django и микросервис уведомлений живут в разных процессах. Чтобы «сообщить» о заказе, можно было бы вызывать HTTP `POST` из Django. Но:

- Django должен знать URL сервиса, ретраи, таймауты;
- если Notification Service временно недоступен, вызов падает — легко потерять событие;
- связь получается жёсткая «точка–точка».

**С брокером (NATS):** Django **публикует сообщение** в брокер. Notification Service **подписан** на нужные темы и **сам** забирает сообщения, когда готов. Сервисы слабо связаны.

**JetStream** — режим NATS с **персистентностью**: сообщения сохраняются на стороне сервера, пока потребитель их не обработает и не подтвердит. Если микросервис перезапустился, он может дочитать непрочитанное.

---

## 9. Упрощённая схема потока данных (NATS)

```
Пользователь оформляет заказ в Django
        │
        ▼
Django сохраняет Order в SQLite (models.Order)
        │
        ▼
Срабатывает сигнал post_save (signals.py)
        │
        ▼
Вызов publish_order_* (nats_events.py) → JSON в NATS JetStream
        │
        ▼
Сервер NATS хранит сообщение в stream FLOWERSHOP (subject flowershop.orders.*)
        │
        ▼
Notification Service: фоновая задача run_nats_consumer() делает pull + fetch
        │
        ▼
Разбор JSON → запись Notification в PostgreSQL
        │
        ▼
msg.ack() — брокеру: «сообщение обработано»
```

---

## 10. Термины NATS / JetStream

| Термин | Смысл |
|--------|--------|
| **Subject (тема)** | Строка-адрес сообщения, например `flowershop.orders.created`. |
| **Stream** | Именованный поток в JetStream. У нас stream **`FLOWERSHOP`**, маска **`flowershop.orders.>`**. |
| **Символ `>`** | Wildcard «всё, что дальше по иерархии». `flowershop.orders.>` совпадает с `flowershop.orders.created`, `flowershop.orders.status_changed` и т.д. |
| **Publish (JetStream)** | `js.publish(...)` — сообщение попадает в stream и получает подтверждение (ack от сервера). |
| **Consumer** | Подписка с именем и правилами доставки. У нас **durable** consumer `notification-service`. |
| **Pull subscribe** | Потребитель **сам запрашивает** пачку сообщений (`fetch`). |
| **ACK / NAK** | **ack** — «обработал успешно». **nak** — «ошибка, можно отдать снова позже». |

---

## 11. Django: от сохранения заказа до публикации

### 11.1. Регистрация сигналов

Файл `flowershop/main/apps.py`:

```python
class MainConfig(AppConfig):
    name = 'main'

    def ready(self):
        import main.signals
```

При старте Django импортируется `signals.py`, регистрируя обработчики.

### 11.2. Сигнал `post_save` на модели `Order`

Файл `flowershop/main/signals.py`:

```python
@receiver(post_save, sender=Order)
def order_post_save(sender, instance, created, **kwargs):
    if created:
        publish_order_created(instance)
    else:
        if instance.tracker.has_changed("status"):
            old_status = instance.tracker.previous("status")
            publish_order_status_changed(instance, old_status)
```

- **`created=True`** → событие «заказ создан».
- **Обновление + смена статуса** → событие «статус изменён».
- Другие правки заказа без смены статуса второе событие **не** шлют.

### 11.3. Модель `Order` (фрагмент)

В `flowershop/main/models.py` у `Order` есть `tracker = FieldTracker(fields=["status"])` (из `django-model-utils`). Без этого в `post_save` нельзя надёжно узнать «старый» и «новый» статус.

### 11.4. Публикация: `nats_events.py`

Файл `flowershop/main/nats_events.py`.

**Константы:**

```python
SUBJECT_ORDER_CREATED = "flowershop.orders.created"
SUBJECT_ORDER_STATUS_CHANGED = "flowershop.orders.status_changed"
STREAM_NAME = "FLOWERSHOP"
```

**`publish_order_created(order)`** собирает payload:

```python
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
```

**`publish_order_status_changed(order, old_status)`** добавляет `old_status`, `new_status` и `notification_status` — маппинг Django-статусов в термины Notification Service:

```python
status_map = {
    "new": "confirmed",
    "processing": "gathering",
    "delivering": "out_for_delivery",
    "completed": "delivered",
    "cancelled": "cancelled",
}
```

**Почему `threading.Thread` + `asyncio.run`?**

- Библиотека `nats-py` асинхронная (`await nats.connect`, `await js.publish`).
- Django views и сигналы — синхронные.
- `_run_async(coro)` запускает корутину в отдельном потоке через `asyncio.run`, чтобы не блокировать HTTP-ответ.

**`_ensure_stream_and_publish(subject, payload)`** (пошагово):

1. `nats.connect(settings.NATS_URL)` — TCP к брокеру.
2. `nc.jetstream()` — контекст JetStream.
3. `js.add_stream(name=FLOWERSHOP, subjects=["flowershop.orders.>"])` — создать stream, если ещё нет.
4. `json.dumps(payload).encode()` — тело сообщения в байтах.
5. `await js.publish(subject, data)` — публикация в конкретную тему.
6. `await nc.close()` — закрыть соединение.

---

## 12. Notification Service: приём и обработка

### 12.1. Когда стартует consumer

В `notification-service/app/main.py`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer_task = asyncio.create_task(run_nats_consumer())
    yield
    consumer_task.cancel()
```

При старте FastAPI создаётся фоновая задача `run_nats_consumer()`. При остановке — отменяется.

### 12.2. `run_nats_consumer()` в `nats_consumer.py`

Файл `notification-service/app/nats_consumer.py`.

**Константы:**

```python
NATS_URL = os.environ.get("NATS_URL", "nats://localhost:4222")
SUBJECT_ORDERS = "flowershop.orders.>"
STREAM_NAME = "FLOWERSHOP"
CONSUMER_NAME = "notification-service"
```

**Внешний `while True`:** устойчивость к обрывам связи — при ошибке подключения ждём 10 секунд и пробуем снова.

**Внутри успешного подключения:**

1. `nats.connect(NATS_URL)`.
2. `js.add_stream(...)` — та же конфигурация stream.
3. `pull_subscribe(SUBJECT_ORDERS, durable=CONSUMER_NAME, stream=STREAM_NAME)`:
   - подписка на **все** сообщения под `flowershop.orders.>`;
   - `durable="notification-service"` — JetStream запоминает offset.
4. Цикл `fetch(batch=5, timeout=5.0)`:
   - раз в до 5 секунд может прийти пусто → `TimeoutError` → `continue`.
5. Для каждого сообщения:
   - `json.loads(msg.data.decode())` → `payload`;
   - `await _handle_order_event(payload)` — бизнес-логика;
   - `await msg.ack()` — подтверждение;
   - при битом JSON — **ack** (чтобы не зациклиться);
   - при ошибке обработки — **nak** (повторная доставка).

### 12.3. `_handle_order_event(payload)`

1. Читает `order_id`.
2. Строит `client_id`: `user_{id}` или `email_{email}` или `order_{id}`.
3. Маппит статус через `STATUS_MAP` в enum `OrderStatus`.
4. Формирует текст сообщения (эмодзи + человекочитаемая строка).
5. Создаёт запись `Notification` в PostgreSQL.

**Результат:** таблица уведомлений обновляется **без** прямого HTTP-вызова из Django.

---

## 13. Сравнение двух подходов

| Критерий | Reviews (HTTP) | Notifications (NATS) |
|----------|---------------|---------------------|
| **Тип связи** | Синхронная (запрос-ответ) | Асинхронная (fire-and-forget) |
| **Протокол** | HTTP REST | NATS JetStream |
| **Библиотека в Django** | `requests` | `nats-py` (async) |
| **Файл-клиент** | `reviews_client.py` | `nats_events.py` |
| **Точка вызова** | `views.py` (при загрузке страницы / POST формы) | `signals.py` (post_save на Order) |
| **Если сервис недоступен** | Пустая страница отзывов (graceful degradation) | Сообщение буферизуется в NATS, обработается позже |
| **Гарантия доставки** | Нет (если сервис упал — ошибка) | Да (JetStream хранит до ack) |
| **Когда использовать** | Нужен немедленный ответ пользователю | Фоновая обработка, уведомления, аналитика |

---

## 14. Переменные окружения

| Переменная | Где используется | Назначение |
|------------|-----------------|------------|
| `NATS_URL` | Django, Notification Service | Строка подключения к NATS. Docker: `nats://nats:4222`, локально: `nats://localhost:4222` |
| `REVIEWS_SERVICE_URL` | Django | URL Reviews Service. Docker: `http://reviews-service:8000`, локально: `http://localhost:8000` |
| `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_HOST`, `DB_PORT` | Reviews Service, Notification Service | Подключение к PostgreSQL |

---

## 15. Практическая проверка

1. Поднять стек: `docker compose up -d` из корня репозитория.
2. Открыть http://localhost:8002 — Django-монолит.
3. **Проверка Reviews (HTTP):**
   - Перейти на страницу отзывов → должны загрузиться отзывы из микросервиса.
   - Отправить новый отзыв → он появится на странице (или ошибка валидации).
   - Прямой запрос: `GET http://localhost:8000/reviews` — JSON от Reviews Service.
   - Swagger: http://localhost:8000/docs
4. **Проверка Notifications (NATS):**
   - Оформить заказ (пользователь залогинен, корзина не пуста).
   - Запрос: `GET http://localhost:8001/notifications?limit=20` — должна появиться запись с `order_id`.
   - В админке Django изменить статус заказа → новая запись в уведомлениях.
   - Swagger: http://localhost:8001/docs
5. Мониторинг NATS: http://localhost:8222

---

## 16. Файлы, которые трогать при расширении

| Задача | Файл |
|--------|------|
| Новый HTTP-эндпоинт в Reviews | `docker-practice/app/main.py` + `crud.py` + `schemas.py` |
| Новый вызов Reviews из Django | `flowershop/main/reviews_client.py` + `views.py` |
| Новое поле в событии NATS | `flowershop/main/nats_events.py` + `notification-service/app/nats_consumer.py` |
| Новый тип события NATS | Новый subject + добавить маску в `subjects` stream (если не входит в `flowershop.orders.>`) |
| Другой микросервис-подписчик | Новый consumer / новая durable-группа, тот же stream или другой subject |

---

## 17. Сводка: что сказать преподавателю одним абзацем

> В проекте два микросервиса подключены к Django-монолиту разными способами. **Reviews Service** связан по **HTTP**: Django через `reviews_client.py` делает синхронные `GET`/`POST` запросы к FastAPI-сервису отзывов; если сервис недоступен, страница отзывов просто показывается пустой. **Notification Service** связан через **NATS JetStream**: при создании или смене статуса заказа Django через `post_save` сигнал публикует JSON в темы `flowershop.orders.created` / `flowershop.orders.status_changed`; сообщения попадают в stream `FLOWERSHOP`; микросервис на FastAPI при старте поднимает durable pull-consumer, периодически забирает сообщения, пишет уведомления в свою БД и отправляет ack. HTTP выбран для отзывов, потому что нужен немедленный ответ пользователю; брокер — для уведомлений, потому что это фоновая задача с гарантией доставки и слабой связностью.

---

*Документ соответствует коду в репозитории `docker-flowershop`: Django (`main/reviews_client.py`, `main/nats_events.py`, `main/signals.py`, `main/views.py`), Reviews Service (`docker-practice/app/main.py`), Notification Service (`notification-service/app/nats_consumer.py`, `notification-service/app/main.py` lifespan).*
