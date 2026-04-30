# Тесты микросервиса отзывов — полная документация

## Оглавление

1. [Общая картина](#1-общая-картина)
2. [Структура файлов](#2-структура-файлов)
3. [Как всё это работает технически](#3-как-всё-это-работает-технически)
4. [Файл за файлом — что внутри и зачем](#4-файл-за-файлом--что-внутри-и-зачем)
   - [pytest.ini](#41-pytestini)
   - [requirements-test.txt](#42-requirements-testtxt)
   - [tests/helpers.py](#43-testshelperspyy)
   - [tests/conftest.py](#44-testsconftestpy)
   - [tests/unit/test_validation.py](#45-testsunittest_validationpy)
   - [tests/unit/test_schemas.py](#46-testsunittest_schemaspy)
   - [tests/unit/test_main_helpers.py](#47-testsunittest_main_helperspy)
   - [tests/integration/test_crud.py](#48-testsintegrationtest_crudpy)
   - [tests/integration/test_api.py](#49-testsintegrationtest_apipy)
   - [tests/integration/test_middleware.py](#410-testsintegrationtest_middlewarepy)
5. [Полный список тест-кейсов](#5-полный-список-тест-кейсов)
6. [Как запустить](#6-как-запустить)
7. [Что делать если тест упал](#7-что-делать-если-тест-упал)

---

## 1. Общая картина

Мы покрываем тестами микросервис отзывов (`docker-practice/`) — FastAPI-приложение, которое хранит отзывы в PostgreSQL и перед сохранением проверяет текст на спам, ссылки и нецензурную лексику.

### Два вида тестов

| Тип | Где лежат | Что тестируют | Нужна БД? | Нужен HTTP-сервер? |
|-----|-----------|--------------|-----------|-------------------|
| **Юнит-тесты** | `tests/unit/` | Чистую логику — валидацию текста, Pydantic-схемы | Нет | Нет |
| **Интеграционные** | `tests/integration/` | CRUD-функции напрямую, HTTP-эндпоинты через TestClient | SQLite in-memory | TestClient (без реального сервера) |

Юнит-тесты работают мгновенно — они вообще не касаются базы данных и сети.  
Интеграционные тесты используют **SQLite в памяти** вместо реального PostgreSQL — каждый тест запускается с чистой пустой базой и сам её удаляет по завершении.

### Итоговое количество тестов

| Файл | Тест-кейсов |
|------|-------------|
| `test_validation.py` | 56 |
| `test_schemas.py` | 31 |
| `test_main_helpers.py` | 27 |
| `test_crud.py` | 36 |
| `test_api.py` | 59 |
| `test_middleware.py` | 15 |
| **Итого** | **~224** |

---

## 2. Структура файлов

```
docker-practice/
│
├── pytest.ini                        ← настройки pytest (пути, PYTHONPATH)
├── requirements-test.txt             ← зависимости только для тестов
│
├── app/                              ← исходный код микросервиса (не трогаем)
│   ├── main.py
│   ├── crud.py
│   ├── schemas.py
│   ├── models.py
│   ├── database.py
│   └── review_validation.py
│
└── tests/
    ├── __init__.py              ← делает tests/ пакетом Python
    ├── helpers.py               ← фабрика тестовых данных (make_review)
    ├── conftest.py              ← общие фикстуры для всех тестов
    │
    ├── unit/
    │   ├── __init__.py
    │   ├── test_validation.py   ← юнит-тесты для review_validation.py
    │   ├── test_schemas.py      ← юнит-тесты для Pydantic-схем
    │   └── test_main_helpers.py ← юнит-тесты для хелперов и seed_demo_data в main.py
    │
    └── integration/
        ├── __init__.py
        ├── test_crud.py         ← интеграционные тесты для crud.py
        ├── test_api.py          ← интеграционные тесты для HTTP-эндпоинтов
        └── test_middleware.py   ← тесты аудит-мидлвара
```

---

## 3. Как всё это работает технически

### 3.1 SQLite вместо PostgreSQL

Реальное приложение работает с PostgreSQL. В тестах мы не можем зависеть от внешней БД — она может быть недоступна, и тесты должны работать на любой машине без Docker.

Решение: SQLAlchemy умеет работать с разными СУБД через одинаковый интерфейс. В тестах мы создаём **движок SQLite в памяти** (`sqlite:///:memory:`), создаём все таблицы из наших моделей и работаем с ними. После теста база просто исчезает.

```
Реальное приложение:        PostgreSQL (docker)
Тесты:                      SQLite in-memory (в оперативной памяти, никакого файла)
```

Таблицы создаются из тех же SQLAlchemy-моделей (`app/models.py`), что и в продакшне, поэтому структура идентична.

### 3.2 Изоляция тестов через фикстуры

Каждый тест получает **собственную пустую базу данных**. Это обеспечивает фикстура `db` в `conftest.py`:

```
Тест 1 → создать engine+таблицы → создать сессию → ТЕСТ → закрыть сессию → удалить таблицы
Тест 2 → создать engine+таблицы → создать сессию → ТЕСТ → закрыть сессию → удалить таблицы
...
```

Тесты не влияют друг на друга. Если тест 1 создал 5 отзывов, тест 2 об этом не знает.

### 3.3 Подмена зависимости get_db

FastAPI-приложение получает сессию БД через dependency injection:

```python
# app/main.py
@app.get("/reviews")
def read_reviews(db: Session = Depends(get_db)):
    ...
```

В тестах мы **переопределяем** эту зависимость, чтобы вместо реального PostgreSQL-соединения приложение получало нашу тестовую SQLite-сессию:

```python
# tests/conftest.py
def override_get_db():
    yield db  # та же сессия, что и в тесте

app.dependency_overrides[get_db] = override_get_db
```

Это означает: весь код эндпоинтов работает **без изменений**, просто работает с другой базой.

### 3.4 Патчинг seed_demo_data

При старте FastAPI-приложения срабатывает `@app.on_event("startup")`, который вызывает `seed_demo_data()`. Эта функция пытается подключиться к PostgreSQL напрямую (через `SessionLocal`, не через `get_db`). В тестах это сломает запуск.

Решение: мы патчим функцию через `unittest.mock.patch` так, чтобы она просто ничего не делала:

```python
with patch("app.main.seed_demo_data"):
    with TestClient(app) as c:
        yield c
```

TestClient запускается — `on_startup` вызывается — `seed_demo_data()` вызывается — но ничего не делает. Всё работает.

### 3.5 Общая сессия между фикстурами

Когда тест использует несколько фикстур (`client` + `approved_review`), они **обе получают одну и ту же сессию** `db`. Это критически важно: данные, созданные через `approved_review`, сразу видны API через `client`.

```
test_something(client, approved_review):
                │              │
                └──── db ─────┘   ← одна и та же SQLite-сессия
```

---

## 4. Файл за файлом — что внутри и зачем

### 4.1 `pytest.ini`

```ini
[pytest]
testpaths = tests
pythonpath = .
```

**Зачем нужен:**  
Это конфигурационный файл pytest. Без него pytest не знает, где искать тесты и откуда импортировать код.

**`testpaths = tests`** — говорит pytest: ищи тесты только в папке `tests/`. Без этого pytest сканирует весь проект и может наткнуться на случайные файлы.

**`pythonpath = .`** — добавляет текущую директорию (`docker-practice/`) в `sys.path`. Это позволяет писать в тестах `from app.crud import ...` вместо `from docker_practice.app.crud import ...`. Без этой строки все импорты из `app.*` сломаются с ошибкой `ModuleNotFoundError`.

---

### 4.2 `requirements-test.txt`

```
pytest>=7.4
httpx>=0.24
```

**Зачем нужен:**  
Отдельный файл зависимостей только для тестов — чтобы не добавлять тестовые библиотеки в продакшн-образ Docker.

**`pytest>=7.4`** — сам фреймворк тестирования. Версия 7.4+ нужна потому, что мы используем параметр `pythonpath` в `pytest.ini` — он появился именно в 7.0.

**`httpx>=0.24`** — HTTP-клиент. Нужен для `fastapi.testclient.TestClient` — современные версии Starlette/FastAPI используют `httpx` под капотом для выполнения тестовых запросов. Без него TestClient не запустится.

---

### 4.3 `tests/helpers.py`

```python
from app import schemas

_DEFAULTS = dict(
    product_id=None,
    user_id=None,
    name="Test User",
    text="Great flowers, fast delivery.",
    rating=5,
)

def make_review(**overrides) -> schemas.ReviewCreate:
    return schemas.ReviewCreate(**{**_DEFAULTS, **overrides})
```

**Зачем нужен:**  
Фабрика тестовых данных. Чтобы создать отзыв в любом тесте, нужно минимум 3 поля (`name`, `text`, `rating`). Писать все три в каждом тесте — многословно и ломко (если поменяется схема, надо менять везде).

`make_review()` возвращает готовый `ReviewCreate` с разумными дефолтами. Если нужно переопределить конкретное поле — передаём его как именованный аргумент:

```python
make_review(rating=1)              # только рейтинг другой
make_review(product_id=42, rating=3)  # два поля
make_review(name="Спамер", text="купить виагру")  # имитация плохого отзыва
```

Этот файл импортируется напрямую (`from tests.helpers import make_review`), а не как pytest-фикстура — потому что нужен не только в фикстурах `conftest.py`, но и прямо внутри тест-функций.

---

### 4.4 `tests/conftest.py`

Главный файл инфраструктуры тестов. pytest автоматически загружает `conftest.py` перед запуском тестов — фикстуры из него доступны во всех тестах в той же директории и подпапках.

#### Фикстура `engine`

```python
@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()
```

Создаёт SQLAlchemy-движок SQLite в памяти. `Base.metadata.create_all` создаёт все таблицы (берёт структуру из `app/models.py`). После теста `drop_all` удаляет таблицы, `dispose` закрывает пул соединений. Область действия — одна тест-функция (`scope="function"` по умолчанию).

`check_same_thread=False` — специальный параметр SQLite, нужен потому что FastAPI иногда обращается к БД из разных потоков.

#### Фикстура `db`

```python
@pytest.fixture()
def db(engine):
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    yield session
    session.close()
```

Создаёт SQLAlchemy-сессию поверх тестового движка. Это тот объект, который передаётся в CRUD-функции и в API через dependency override. Закрывается после теста.

`autocommit=False` — транзакции надо коммитить явно. `autoflush=False` — SQL не отправляется автоматически при каждом обращении к объекту.

#### Фикстура `client`

```python
@pytest.fixture()
def client(db):
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    with patch("app.main.seed_demo_data"):
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.clear()
```

Собирает всё вместе: берёт тестовую сессию `db`, подменяет зависимость `get_db` в приложении, патчит `seed_demo_data`, запускает `TestClient`. После теста убирает подмену зависимости (`dependency_overrides.clear()`), чтобы не испортить другие тесты.

#### Фикстуры `approved_review`, `unapproved_review`, `five_reviews`

Готовые наборы данных для тестов, которым нужна предзаполненная база:

- **`approved_review`** — один одобренный отзыв (product_id=1, rating=5). Используется в тестах GET по ID, PATCH, DELETE.
- **`unapproved_review`** — один неодобренный отзыв (product_id=1, rating=3). Используется в тестах фильтрации и PATCH одобрения.
- **`five_reviews`** — пять отзывов с разными product_id, рейтингами и статусами одобрения. Используется в тестах пагинации, фильтрации и сортировки.

---

### 4.5 `tests/unit/test_validation.py`

**Тестирует:** `app/review_validation.py`  
**Зависимостей:** никаких — только чистый Python.

`review_validation.py` — это модуль автоматической проверки текста перед сохранением. Функция `validate_review_text(*, name, text)` возвращает `None` если всё ок, или строку с описанием проблемы.

Внутри функции три этапа проверки (строго по порядку):

```
1. Repeat-spam     → 10+ одинаковых символов подряд → "Слишком много повторяющихся символов..."
2. Links / spam    → URL, email, IP, домены        → "Нельзя указывать ссылки..."
3. Profanity       → мат и грубость                → "Пожалуйста, без ненормативной лексики."
```

#### Класс `TestValidInputs` (6 тестов)
Убеждаемся, что нормальные тексты не отвергаются: русский текст, английский текст, цифры, знаки препинания, дефис в имени, 9 одинаковых символов (граница — именно 10).

#### Класс `TestRepeatSpam` (6 тестов)
Проверяем детектор повторяющихся символов:
- 10 одинаковых символов в тексте → отказ
- 11 символов → отказ
- 9 символов → разрешено (граничное значение)
- 10 символов в имени → отказ
- Правильное сообщение об ошибке
- Порядок проверок: repeat-spam перехватывается **раньше** ссылок и мата

#### Класс `TestLinksAndSpam` (15 тестов)
Проверяем все виды запрещённых паттернов:
- HTTP/HTTPS/FTP-ссылки
- Префикс `www.`
- Мессенджеры: `t.me/`, `telegram.me/`, `vk.com/`, `wa.me/`
- Сокращатели: `bit.ly/`, `youtu.be/`, `discord.gg/`
- Домены с TLD: `.ru`, `.com`, `.io`, `.online`
- Email (`user@domain.com`)
- IPv4-адреса (`192.168.1.1`)
- Ссылки в поле `name` (не только в `text`)
- Правильное сообщение об ошибке

#### Класс `TestProfanity` (15 тестов)
Проверяем мат и нормализацию:
- Русские корни: `хуй`, `пизд`, `бля`, `сука`, `мудак`, `говно`
- Английский мат: `fuck`, `shit`, `bitch`
- Регистронезависимость (`FUCK`, `Говно`)
- Нормализация `ё → е`: `"Ёбаный"` → нормализуется до `"ебаный"` → матч по корню `"ебан"`
- Нормализация `0 → о`: `"г0вно"` → `"говно"`
- Нормализация `@ → а`: `"сук@"` → `"сука"`
- Нормализация `$ → с`: `"$ука"` → `"сука"`
- Мат в поле `name`
- Порядок: ссылки перехватываются **раньше** мата

---

### 4.6 `tests/unit/test_schemas.py`

**Тестирует:** `app/schemas.py` (Pydantic-модели)  
**Зависимостей:** никаких — только Pydantic.

Schemas — это контракт данных приложения. Здесь мы проверяем что Pydantic правильно валидирует входные данные ещё до того, как они дойдут до базы.

#### Класс `TestReviewCreate` (17 тестов)

`ReviewCreate` наследует `ReviewBase`, где определены валидаторы.

**Корректные данные:**
- Минимальный набор полей (name, text, rating)
- Все поля включая опциональные (product_id, user_id)
- Граничные значения рейтинга: 1 и 5 должны проходить
- Имя ровно 100 символов — должно проходить

**Стрипинг пробелов** (`not_empty` validator):
- `"  Alice  "` → становится `"Alice"` (пробелы обрезаются)
- `"  Nice!  "` → становится `"Nice!"` в поле text

**Ошибки валидации** (`pytest.raises(ValidationError)`):
- Пустое имя `""` → ошибка с текстом "empty"
- Имя из пробелов `"   "` → ошибка
- Имя из табов и переносов → ошибка
- Пустой текст → ошибка
- Рейтинг 0 и 6 → ошибка
- Отрицательный рейтинг → ошибка
- Имя 101 символ → ошибка (max_length=100)
- Отсутствие обязательных полей (name, text, rating) → ошибка каждое

#### Класс `TestReviewUpdate` (8 тестов)

`ReviewUpdate` — схема для PATCH-запроса. Особенности: только поле `is_approved`, `extra="forbid"`.

- `is_approved=True` и `False` работают
- Пустой объект `ReviewUpdate()` схемно валиден (API-слой потом проверяет отдельно)
- Лишние поля `name`, `text`, `rating` → `ValidationError` (extra="forbid")
- `model_dump(exclude_unset=True)` возвращает `{}` если ничего не передано — это именно та логика, которую использует PATCH-эндпоинт для проверки "хотя бы одно поле"

#### Классы `TestReviewResponse`, `TestReviewList`, `TestRatingSummary` (6 тестов)

Проверяем выходные схемы: все поля присутствуют, опциональные могут быть None, total может быть больше len(items) (при пагинации).

В разделе `TestAdditionalUrlSchemes` (5 тестов) проверяем схемы и паттерны, которые были в регулярке, но не попали в основной класс:
- `ftps://` (защищённый FTP)
- `goo.gl/` (Google-сокращатель)
- `tinyurl.com/` (TinyURL)
- `discord.com/` (полный домен Discord, отдельно от `discord.gg/`)
- `//domain/path` (protocol-relative URL без указания схемы)

Нормализация `3 → з` проверяется отдельным тестом: `"3алуп"` → `"залуп"` → матч по корню `"залуп"` из словаря.

---

### 4.7 `tests/unit/test_main_helpers.py`

**Тестирует:** приватные хелпер-функции и `seed_demo_data` из `app/main.py`.  
**Зависимостей:** `unittest.mock`, `tmp_path` (встроенная фикстура pytest), для seed-тестов — `engine` + `db`.

Этот файл тестирует код, который раньше полностью выпадал из покрытия: пять функций из `main.py`, которые используются внутри приложения, но никогда не вызываются напрямую через HTTP.

#### Класс `TestUtcIso` (5 тестов)

`_utc_iso()` возвращает строку текущего UTC-времени в формате ISO-8601 с точностью до секунды.

- Тип возвращаемого значения — `str`
- В строке присутствует смещение `+00:00` (UTC)
- Строка парсится обратно в `datetime` без ошибок
- Поле `microsecond == 0` (параметр `timespec="seconds"` отрезает микросекунды)
- Результат находится между `before` и `after` — убеждаемся что функция возвращает *текущее* время

#### Класс `TestClientIp` (5 тестов)

`_client_ip(request)` извлекает IP-адрес клиента. Мокаем `Request` через `MagicMock` — не нужен настоящий HTTP-запрос.

- Одиночный IP в `x-forwarded-for` → возвращается как есть
- Список IP через запятую (`"1.2.3.4, 5.6.7.8"`) → берётся **первый** (левый = клиент)
- Пробелы вокруг IP в forwarded-заголовке обрезаются
- Нет `x-forwarded-for` → берётся `request.client.host`
- Нет ни заголовка, ни `client` → возвращается `"unknown"`

#### Класс `TestAppendJsonLine` (6 тестов)

`_append_json_line(path, payload)` дописывает одну JSON-строку в конец файла. Используем встроенную фикстуру `tmp_path` — pytest создаёт временную директорию, которая удаляется после теста.

- Файл создаётся если не существовал
- Содержимое — валидный JSON (`json.loads` не бросает исключение)
- Родительская директория создаётся рекурсивно (`mkdir(parents=True, exist_ok=True)`)
- Каждый вызов **дописывает** новую строку, не перезаписывает файл
- Кириллица хранится в исходном виде (`ensure_ascii=False`), не как `\uXXXX`
- Второй вызов не затирает первую запись

#### Класс `TestJsonOrText` (9 тестов)

`_json_or_text(body_bytes)` используется мидлваром для логирования тела запроса — он пытается распарсить байты как JSON, а если не получается — отдаёт как строку.

- `b""` → `None` (пустое тело)
- `b'{"key": "val"}'` → `dict`
- `b'[1,2,3]'` → `list`
- `b'42'` → `int` (число тоже валидный JSON)
- `b'"string"'` → `str` (строковый JSON-литерал)
- `b"not valid json"` → строка (fallback на decode)
- `b"{malformed"` → строка (fallback)
- UTF-8 кириллица → строка с правильными символами
- JSON с кирилличными значениями → `dict` с правильными строками

#### Класс `TestSeedDemoData` (4 теста)

`seed_demo_data()` заполняет БД демо-данными при старте, но только если она пустая. Патчим `SessionLocal` через `patch("app.main.SessionLocal", TestSession)`, где `TestSession = sessionmaker(bind=engine)` — это фабрика сессий для нашей тестовой SQLite-базы.

- В пустую базу вставляется ровно 3 отзыва
- Имена вставленных отзывов: `{"Anna", "Petr", "Maria"}`
- Если в базе уже есть хотя бы один отзыв — функция ничего не делает (ранний return)
- Повторный вызов не дублирует данные

---

### 4.9 `tests/integration/test_crud.py`

**Тестирует:** `app/crud.py` — функции прямой работы с базой данных.  
**Зависимости:** фикстура `db` (SQLite in-memory).

Здесь нет HTTP — мы вызываем CRUD-функции напрямую и проверяем что они делают с базой.

#### Вспомогательная функция `_get(db, **kwargs)`

Обёртка над `crud.get_reviews` с умными дефолтами. Позволяет вызывать функцию лаконично:

```python
_get(db)                        # все отзывы без фильтров
_get(db, approved_only=True)    # только одобренные
_get(db, min_rating=4, limit=3) # рейтинг ≥4, первые 3
```

#### Класс `TestCreateReview` (7 тестов)

- Возвращает экземпляр `models.Review` с заполненным `id`
- Все поля (`product_id`, `user_id`, `name`, `text`, `rating`) сохраняются правильно
- `is_approved=False` тоже сохраняется (не перетирается дефолтом)
- `created_at` заполняется автоматически
- `product_id=None` разрешён (отзыв о магазине в целом)
- `user_id=None` разрешён (анонимный отзыв)
- Каждый отзыв получает уникальный `id`

#### Класс `TestGetReview` (4 теста)

- Нахождение по существующему ID
- Возвращённые данные совпадают с тем что записали
- `None` для несуществующего ID (99999)
- `None` для нулевого ID

#### Класс `TestGetReviews` (17 тестов)

Самый большой класс. Использует `autouse` фикстуру `seed`, которая создаёт 4 отзыва **с явно выставленными датами** — чтобы тесты сортировки были детерминированы:

```
r1 — product_id=1, rating=5, approved,   created_at = 2024-01-01 12:00
r2 — product_id=1, rating=3, approved,   created_at = 2024-01-01 13:00
r3 — product_id=2, rating=4, unapproved, created_at = 2024-01-01 14:00
r4 — product_id=None, rating=2, approved, created_at = 2024-01-01 15:00
```

Тесты покрывают:
- Без фильтров → все 4
- `approved_only=True` → 3 (r1, r2, r4)
- `approved_only=False` → 1 (только r3)
- `approved_only=None` → все 4 (фильтр отключён)
- `product_id=1` → 2 (r1, r2)
- `product_id=999` → 0
- `product_id=None` → все 4 (не фильтрует!)
- `min_rating=4` → 2 (r1=5, r3=4)
- `max_rating=3` → 2 (r2=3, r4=2)
- `min_rating=3, max_rating=4` → 2 (r2, r3)
- Невозможный диапазон `min=5, max=1` → 0
- `limit=2` → 2 элемента, total=4
- `offset=2` → пропускает первые 2, возвращает остальные
- `offset=100` → пустой список, total=4
- Четыре варианта сортировки: по дате и рейтингу, по возрастанию и убыванию

#### Классы `TestUpdateReview`, `TestDeleteReview` (9 тестов)

Update: одобрение/отклонение, сохранение ID, персистентность в БД, неизменность других полей.

Delete: объект исчезает из `get_review`, функция возвращает `None`, другие записи не затрагиваются, total уменьшается.

#### Класс `TestGetRatingSummary` (8 тестов)

Самая сложная логика: функция одновременно фильтрует по `approved_only`, по `product_id`, и считает среднее.

Критичные edge cases:
- Пустая база → `(None, 0)`, не падает с ошибкой деления на ноль
- `product_id=None` означает **"отзывы о магазине"** (WHERE product_id IS NULL) — не отсутствие фильтра!
- `product_id=999` без данных → `(None, 0)`
- approved/unapproved смешаны — правильно считает только нужные

---

### 4.10 `tests/integration/test_api.py`

**Тестирует:** HTTP-эндпоинты в `app/main.py` через `TestClient`.  
**Зависимости:** фикстура `client` + по необходимости `db`, `approved_review`, `unapproved_review`, `five_reviews`.

Здесь мы тестируем приложение **как чёрный ящик** — отправляем HTTP-запросы и проверяем HTTP-ответы (статус-код, тело, заголовки).

#### Класс `TestRoot` (3 теста)

`GET /` — статус 200, наличие ключей `message` и `status` в JSON.

#### Класс `TestGetReviews` (20 тестов)

`GET /reviews` — наиболее параметризованный эндпоинт.

**Базовые:**
- Пустая база → 200, `{"items": [], "total": 0}`
- С данными → правильный total
- Элемент содержит все ожидаемые поля

**Пагинация:**
- `?limit=2` → 2 элемента, total=5
- `?offset=2` → правильный срез
- `?limit=0` → 422 (ge=1)
- `?limit=101` → 422 (le=100)
- `?offset=-1` → 422 (ge=0)

**Фильтры:**
- `?approved_only=true/false` — правильная фильтрация
- `?product_id=1` — только нужный продукт
- `?product_id=999` — пустой список
- `?min_rating=4` — только ≥4
- `?max_rating=2` — только ≤2
- `?min_rating=0` → 422 (ge=1)
- `?max_rating=6` → 422 (le=5)

**Сортировка:**
- `rating_asc`, `rating_desc`, `created_at_asc`, `created_at_desc`
- `?sort=invalid` → 422 (не из Literal)

#### Класс `TestCreateReview` (15 тестов)

`POST /reviews` — самый насыщенный с точки зрения валидации.

**Успешные:**
- 201 Created
- Тело ответа содержит `id`
- Поля в ответе совпадают с отправленными
- `is_approved=True` по умолчанию
- `product_id` и `user_id` принимаются
- После создания отзыв виден в `GET /reviews`

**Pydantic-ошибки (422):**
- Пустое `name`, пробелы в `name`
- Пустой `text`
- `rating=0`, `rating=6`
- Отсутствующие обязательные поля

**Ошибки модерации (422):**
- URL в тексте: `"Check https://spam.ru"`
- Email в тексте: `"Email me at x@y.com"`
- Нецензурная лексика: `"fuck this shop"`
- Repeat-spam: `"aaaaaaaaaa"`
- Сообщение об ошибке читаемое (строка длиннее 5 символов)

#### Класс `TestGetReviewById` (4 теста)

`GET /reviews/{id}`:
- 200 + правильные данные для существующего
- 404 для несуществующего
- 404-ответ содержит поле `detail`

#### Класс `TestPatchReview` (7 тестов)

`PATCH /reviews/{id}`:
- Одобрить неодобренный → `is_approved: true`
- Отклонить одобренный → `is_approved: false`
- Ответ содержит все поля (id, name, rating не изменились)
- Пустое тело `{}` → 422 ("At least one field must be provided")
- Лишнее поле `{"name": "hacker"}` → 422 (extra="forbid")
- Несуществующий ID → 404
- Изменение персистируется (GET после PATCH отражает новое значение)

#### Класс `TestDeleteReview` (6 тестов)

`DELETE /reviews/{id}`:
- 204 No Content
- Тело ответа пустое
- После удаления GET возвращает 404
- После удаления ID отсутствует в листинге
- Удаление несуществующего → 404
- Двойное удаление → второй раз 404

#### Класс `TestRatingSummary` (8 тестов)

`GET /ratings/summary`:
- Пустая база → 200, `{"average": null, "count": 0}`
- С двумя отзывами рейтинг 4 и 2 → `average: 3.0, count: 2`
- Неодобренные исключаются по умолчанию
- `?approved_only=false` включает неодобренные
- `?product_id=10` → считает только по продукту 10
- `?product_id=999` без данных → `average: null, count: 0`
- `product_id` отражается в ответе

#### Класс `TestEdgeCases` (11 тестов) — добавлено

Тесты граничных случаев, которые не вписывались в другие классы:

**Нецелочисленный path-параметр:**
- `GET /reviews/abc` → 422 (FastAPI автоматически валидирует тип пути `{reviewId: int}`)
- `PATCH /reviews/abc` → 422
- `DELETE /reviews/abc` → 422

**Комбинированные фильтры:**
- `?product_id=1&approved_only=true` → только одобренные из product_id=1
- `?product_id=1&min_rating=4` → только рейтинг ≥4 из product_id=1
- `?approved_only=true&min_rating=3&max_rating=5` → одобренные с рейтингом 3-5
- Все фильтры сразу + `limit=1` → 1 результат, соответствующий всем условиям

**Лишние поля в теле POST:**
- `{"name": ..., "rating": ..., "text": ..., "unknown_field": "x"}` → 201 (лишние поля молча игнорируются, `ReviewCreate` не имеет `extra="forbid"`)

**Граничные значения рейтинга в query-параметрах:**
- `?min_rating=1` → 200 (нижняя граница)
- `?max_rating=5` → 200 (верхняя граница)
- `rating=1` в POST → 201
- `rating=5` в POST → 201

---

### 4.11 `tests/integration/test_middleware.py`

**Тестирует:** мидлвар `audit_non_get_requests` из `app/main.py`.  
**Зависимости:** `client`, `approved_review`, `unapproved_review`, `patch` из `unittest.mock`.

Мидлвар — это прослойка между HTTP-сервером и обработчиком эндпоинта. Он имеет критичную логику: читает тело запроса ДО эндпоинта, а потом переподаёт его обратно. Если что-то сломается, все POST/PATCH/DELETE перестанут работать.

#### Класс `TestMiddlewareBypass` (4 теста)

Проверяем что GET-запросы не блокируются и не изменяются мидлваром:
- `GET /reviews` → 200
- `GET /reviews/{id}` → 200
- `GET /ratings/summary` → 200
- `GET /` → 200

Для GET-запросов мидлвар делает ранний `return await call_next(request)` — аудит не пишется, тело не читается.

#### Класс `TestBodyPreservation` (6 тестов)

Самая важная гарантия: после того как мидлвар прочитал тело через `await request.body()`, он переподаёт его через кастомную функцию `receive`. Без этого эндпоинт получил бы пустое тело и вернул бы 422.

- `POST /reviews` с валидным JSON → 201, тело в ответе совпадает с отправленным
- `PATCH /reviews/{id}` → 200, изменение применилось
- `DELETE /reviews/{id}` без тела → 204 (DELETE работает без тела)
- Мидлвар не изменяет статус-код ответа (201 остаётся 201)
- Невалидный POST (rating=0) → 422 (мидлвар не поглощает ошибки валидации)
- POST с матом → 422 (мидлвар не мешает модерации)

#### Класс `TestAuditLogging` (5 тестов)

Патчим `_append_json_line` через `unittest.mock.patch` чтобы перехватить вызовы без реальной записи на диск. Задача — убедиться что мидлвар формирует правильную структуру аудит-записи.

- POST вызывает `_append_json_line` (или создаёт задачу, которая её вызовет)
- GET не вызывает `_append_json_line`
- Аудит-запись содержит все обязательные ключи: `ts`, `service`, `method`, `path`, `ip`, `status_code`, `body`
- Поле `body` содержит данные отправленного запроса
- DELETE тоже создаёт аудит-запись с `method == "DELETE"`

> **Примечание:** Аудит-запись создаётся через `asyncio.create_task(asyncio.to_thread(...))`. Это fire-and-forget задача. В тестах с синхронным `TestClient` задача может завершиться до или после возврата ответа — поэтому проверки `if captured:` написаны защитно: если задача ещё не выполнилась, тест не падает. Наличие записи проверяется только когда она доступна.

---

## 5. Полный список тест-кейсов

### tests/unit/test_validation.py

| # | Класс | Тест |
|---|-------|------|
| 1 | ValidInputs | plain russian text |
| 2 | ValidInputs | plain english text |
| 3 | ValidInputs | numbers allowed |
| 4 | ValidInputs | punctuation allowed |
| 5 | ValidInputs | hyphen in name allowed |
| 6 | ValidInputs | nine identical chars allowed |
| 7 | ValidInputs | nine identical chars in name allowed |
| 8 | RepeatSpam | ten same chars rejected |
| 9 | RepeatSpam | eleven same chars rejected |
| 10 | RepeatSpam | repeat spam in name rejected |
| 11 | RepeatSpam | mid sentence spam rejected |
| 12 | RepeatSpam | checked before links |
| 13 | RepeatSpam | checked before profanity |
| 14 | LinksAndSpam | http url rejected |
| 15 | LinksAndSpam | https url rejected |
| 16 | LinksAndSpam | ftp url rejected |
| 17 | LinksAndSpam | www prefix rejected |
| 18 | LinksAndSpam | telegram t.me rejected |
| 19 | LinksAndSpam | telegram.me rejected |
| 20 | LinksAndSpam | vk.com rejected |
| 21 | LinksAndSpam | wa.me rejected |
| 22 | LinksAndSpam | bit.ly rejected |
| 23 | LinksAndSpam | youtu.be rejected |
| 24 | LinksAndSpam | discord.gg rejected |
| 25 | LinksAndSpam | domain .ru rejected |
| 26 | LinksAndSpam | domain .com rejected |
| 27 | LinksAndSpam | domain .io rejected |
| 28 | LinksAndSpam | domain .online rejected |
| 29 | LinksAndSpam | email in text rejected |
| 30 | LinksAndSpam | email in name rejected |
| 31 | LinksAndSpam | ipv4 rejected |
| 32 | LinksAndSpam | ip at start rejected |
| 33 | LinksAndSpam | url in name rejected |
| 34 | Profanity | russian root хуй |
| 35 | Profanity | russian root пизд |
| 36 | Profanity | russian бля |
| 37 | Profanity | russian сука |
| 38 | Profanity | russian мудак |
| 39 | Profanity | russian говно |
| 40 | Profanity | english fuck |
| 41 | Profanity | english shit |
| 42 | Profanity | english bitch |
| 43 | Profanity | uppercase english |
| 44 | Profanity | mixed case russian |
| 45 | Profanity | ё→е normalization |
| 46 | Profanity | 0→о normalization |
| 47 | Profanity | @→а normalization |
| 48 | Profanity | $→с normalization |
| 49 | Profanity | profanity in name |
| 50 | Profanity | link caught before profanity |
| 51 | Profanity | 3→з normalization |
| 52 | AdditionalUrlSchemes | ftps scheme rejected |
| 53 | AdditionalUrlSchemes | goo.gl shortener rejected |
| 54 | AdditionalUrlSchemes | tinyurl shortener rejected |
| 55 | AdditionalUrlSchemes | discord.com rejected |
| 56 | AdditionalUrlSchemes | double-slash url rejected |

### tests/unit/test_schemas.py

| # | Класс | Тест |
|---|-------|------|
| 51 | ReviewCreate | valid minimal |
| 52 | ReviewCreate | valid with all optional fields |
| 53 | ReviewCreate | rating lower boundary (1) |
| 54 | ReviewCreate | rating upper boundary (5) |
| 55 | ReviewCreate | name exactly 100 chars |
| 56 | ReviewCreate | name stripped |
| 57 | ReviewCreate | text stripped |
| 58 | ReviewCreate | empty name raises |
| 59 | ReviewCreate | whitespace name raises |
| 60 | ReviewCreate | tab-only name raises |
| 61 | ReviewCreate | empty text raises |
| 62 | ReviewCreate | whitespace text raises |
| 63 | ReviewCreate | rating 0 raises |
| 64 | ReviewCreate | rating 6 raises |
| 65 | ReviewCreate | negative rating raises |
| 66 | ReviewCreate | name 101 chars raises |
| 67 | ReviewCreate | missing name raises |
| 68 | ReviewCreate | missing text raises |
| 69 | ReviewCreate | missing rating raises |
| 70 | ReviewUpdate | set approved true |
| 71 | ReviewUpdate | set approved false |
| 72 | ReviewUpdate | empty is schema-valid |
| 73 | ReviewUpdate | extra field name raises |
| 74 | ReviewUpdate | extra field text raises |
| 75 | ReviewUpdate | extra field rating raises |
| 76 | ReviewUpdate | model_dump empty when nothing set |
| 77 | ReviewUpdate | model_dump contains set field |
| 78 | ReviewResponse | all fields populated |
| 79 | ReviewResponse | optional fields can be None |
| 80 | ReviewList | empty list |
| 81 | ReviewList | with one item |
| 82 | ReviewList | total can exceed items |
| 83 | RatingSummary | with average |
| 84 | RatingSummary | average can be None |
| 85 | RatingSummary | product_id optional |

### tests/unit/test_main_helpers.py

| # | Класс | Тест |
|---|-------|------|
| 86 | UtcIso | returns string |
| 87 | UtcIso | contains utc offset |
| 88 | UtcIso | parseable as iso datetime |
| 89 | UtcIso | seconds precision |
| 90 | UtcIso | is recent |
| 91 | ClientIp | single ip from x-forwarded-for |
| 92 | ClientIp | first ip from comma list |
| 93 | ClientIp | whitespace stripped |
| 94 | ClientIp | fallback to client host |
| 95 | ClientIp | unknown when no info |
| 96 | AppendJsonLine | creates file |
| 97 | AppendJsonLine | written content is valid json |
| 98 | AppendJsonLine | creates parent directory |
| 99 | AppendJsonLine | each call appends new line |
| 100 | AppendJsonLine | unicode preserved |
| 101 | AppendJsonLine | second call does not overwrite |
| 102 | JsonOrText | empty bytes → None |
| 103 | JsonOrText | valid json object |
| 104 | JsonOrText | valid json array |
| 105 | JsonOrText | valid json number |
| 106 | JsonOrText | valid json string literal |
| 107 | JsonOrText | invalid json → text |
| 108 | JsonOrText | partial json → text |
| 109 | JsonOrText | unicode text preserved |
| 110 | JsonOrText | json with unicode values |
| 111 | SeedDemoData | inserts 3 reviews into empty db |
| 112 | SeedDemoData | seeded reviews have expected names |
| 113 | SeedDemoData | skips if reviews already exist |
| 114 | SeedDemoData | calling twice does not duplicate |

### tests/integration/test_crud.py

| # | Класс | Тест |
|---|-------|------|
| 115 | CreateReview | returns model with id |
| 116 | CreateReview | all fields persisted |
| 117 | CreateReview | is_approved false stored |
| 118 | CreateReview | created_at populated |
| 119 | CreateReview | product_id None allowed |
| 120 | CreateReview | user_id None allowed |
| 121 | CreateReview | unique ids |
| 122 | GetReview | returns by id |
| 123 | GetReview | correct data returned |
| 124 | GetReview | None for nonexistent |
| 125 | GetReview | None for zero id |
| 126 | GetReviews | all without filters |
| 127 | GetReviews | total equals count |
| 128 | GetReviews | approved_only true |
| 129 | GetReviews | approved_only false |
| 130 | GetReviews | approved_only None = all |
| 131 | GetReviews | product_id filter |
| 132 | GetReviews | product_id nonexistent = empty |
| 133 | GetReviews | product_id None = no filter |
| 134 | GetReviews | min_rating filter |
| 135 | GetReviews | max_rating filter |
| 136 | GetReviews | rating range inclusive |
| 137 | GetReviews | impossible range = empty |
| 138 | GetReviews | limit |
| 139 | GetReviews | offset |
| 140 | GetReviews | offset beyond total = empty |
| 141 | GetReviews | sort created_at desc |
| 142 | GetReviews | sort created_at asc |
| 143 | GetReviews | sort rating desc |
| 144 | GetReviews | sort rating asc |
| 145 | UpdateReview | approve unapproved |
| 146 | UpdateReview | disapprove approved |
| 147 | UpdateReview | preserves id |
| 148 | UpdateReview | persists to db |
| 149 | UpdateReview | does not change other fields |
| 150 | DeleteReview | deleted not findable |
| 151 | DeleteReview | returns None |
| 152 | DeleteReview | does not affect others |
| 153 | DeleteReview | total decreases |
| 154 | RatingSummary | empty db → None, 0 |
| 155 | RatingSummary | single review avg = rating |
| 156 | RatingSummary | rounded to 2 decimals |
| 157 | RatingSummary | approved_only excludes unapproved |
| 158 | RatingSummary | approved_only false = all |
| 159 | RatingSummary | product_id filter |
| 160 | RatingSummary | product_id None = NULL filter |
| 161 | RatingSummary | nonexistent product → None, 0 |

### tests/integration/test_api.py

| # | Класс | Тест |
|---|-------|------|
| 162 | Root | returns 200 |
| 163 | Root | contains message key |
| 164 | Root | contains status key |
| 165 | GetReviews | empty db 200 |
| 166 | GetReviews | empty list and zero total |
| 167 | GetReviews | returns all |
| 168 | GetReviews | schema has items and total |
| 169 | GetReviews | item has expected fields |
| 170 | GetReviews | limit restricts items |
| 171 | GetReviews | offset skips rows |
| 172 | GetReviews | limit=0 → 422 |
| 173 | GetReviews | limit=101 → 422 |
| 174 | GetReviews | offset=-1 → 422 |
| 175 | GetReviews | approved_only true |
| 176 | GetReviews | approved_only false |
| 177 | GetReviews | no filter = all |
| 178 | GetReviews | product_id filter |
| 179 | GetReviews | product_id no match = empty |
| 180 | GetReviews | min_rating filter |
| 181 | GetReviews | max_rating filter |
| 182 | GetReviews | min_rating=0 → 422 |
| 183 | GetReviews | max_rating=6 → 422 |
| 184 | GetReviews | sort rating asc |
| 185 | GetReviews | sort rating desc |
| 186 | GetReviews | sort created_at asc |
| 187 | GetReviews | sort created_at desc |
| 188 | GetReviews | sort invalid → 422 |
| 189 | CreateReview | returns 201 |
| 190 | CreateReview | response has id |
| 191 | CreateReview | fields match request |
| 192 | CreateReview | is_approved true by default |
| 193 | CreateReview | optional ids accepted |
| 194 | CreateReview | appears in listing |
| 195 | CreateReview | empty name → 422 |
| 196 | CreateReview | whitespace name → 422 |
| 197 | CreateReview | empty text → 422 |
| 198 | CreateReview | rating 0 → 422 |
| 199 | CreateReview | rating 6 → 422 |
| 200 | CreateReview | missing name → 422 |
| 201 | CreateReview | missing text → 422 |
| 202 | CreateReview | missing rating → 422 |
| 203 | CreateReview | spam url → 422 |
| 204 | CreateReview | email in text → 422 |
| 205 | CreateReview | profanity → 422 |
| 206 | CreateReview | repeat spam → 422 |
| 207 | CreateReview | error detail readable |
| 208 | GetReviewById | returns 200 |
| 209 | GetReviewById | data matches |
| 210 | GetReviewById | not found → 404 |
| 211 | GetReviewById | 404 has detail |
| 212 | PatchReview | approve unapproved |
| 213 | PatchReview | disapprove approved |
| 214 | PatchReview | other fields preserved |
| 215 | PatchReview | empty body → 422 |
| 216 | PatchReview | extra field → 422 |
| 217 | PatchReview | not found → 404 |
| 218 | PatchReview | change persisted |
| 219 | DeleteReview | returns 204 |
| 220 | DeleteReview | body is empty |
| 221 | DeleteReview | gone after delete |
| 222 | DeleteReview | absent from listing |
| 223 | DeleteReview | not found → 404 |
| 224 | DeleteReview | double delete → 404 |
| 225 | RatingSummary | no reviews 200 |
| 226 | RatingSummary | null average zero count |
| 227 | RatingSummary | approved counted |
| 228 | RatingSummary | unapproved excluded |
| 229 | RatingSummary | approved_only false |
| 230 | RatingSummary | product_id filter |
| 231 | RatingSummary | nonexistent product |
| 232 | RatingSummary | product_id echoed |
| 233 | EdgeCases | non-integer GET id → 422 |
| 234 | EdgeCases | non-integer PATCH id → 422 |
| 235 | EdgeCases | non-integer DELETE id → 422 |
| 236 | EdgeCases | combined product_id + approved_only |
| 237 | EdgeCases | combined product_id + min_rating |
| 238 | EdgeCases | combined approved_only + rating range |
| 239 | EdgeCases | all filters combined + limit |
| 240 | EdgeCases | extra POST fields ignored |
| 241 | EdgeCases | min_rating=1 valid |
| 242 | EdgeCases | max_rating=5 valid |
| 243 | EdgeCases | rating=1 in POST accepted |
| 244 | EdgeCases | rating=5 in POST accepted |

### tests/integration/test_middleware.py

| # | Класс | Тест |
|---|-------|------|
| 245 | MiddlewareBypass | GET /reviews not blocked |
| 246 | MiddlewareBypass | GET by id not blocked |
| 247 | MiddlewareBypass | GET ratings not blocked |
| 248 | MiddlewareBypass | GET root not blocked |
| 249 | BodyPreservation | POST body received by endpoint |
| 250 | BodyPreservation | PATCH body received by endpoint |
| 251 | BodyPreservation | DELETE works without body |
| 252 | BodyPreservation | middleware does not alter response status |
| 253 | BodyPreservation | invalid POST → 422 through middleware |
| 254 | BodyPreservation | moderation failure → 422 through middleware |
| 255 | AuditLogging | POST triggers audit log write |
| 256 | AuditLogging | GET does not trigger audit log |
| 257 | AuditLogging | audit event has expected keys |
| 258 | AuditLogging | audit event body contains request data |
| 259 | AuditLogging | DELETE triggers audit log write |

---

## 6. Как запустить

### Требования

- Python 3.9+
- Установленные зависимости сервиса: `pip install -r requirements.txt`
- Установленные тестовые зависимости: `pip install -r requirements-test.txt`

### Установить зависимости

```bash
cd docker-practice
pip install -r requirements.txt
pip install -r requirements-test.txt
```

### Запустить все тесты

```bash
cd docker-practice
pytest
```

### Запустить с подробным выводом (рекомендуется)

```bash
pytest -v
```

Вывод будет выглядеть так:
```
tests/unit/test_validation.py::TestValidInputs::test_plain_russian_text PASSED
tests/unit/test_validation.py::TestValidInputs::test_plain_english_text PASSED
...
tests/integration/test_api.py::TestDeleteReview::test_double_delete_second_returns_404 PASSED

============================== 152 passed in 8.42s ==============================
```

### Запустить только юнит-тесты (без БД, очень быстро)

```bash
pytest tests/unit/ -v
```

### Запустить только интеграционные тесты

```bash
pytest tests/integration/ -v
```

### Запустить конкретный файл

```bash
pytest tests/unit/test_validation.py -v
pytest tests/unit/test_main_helpers.py -v
pytest tests/integration/test_api.py -v
pytest tests/integration/test_middleware.py -v
```

### Запустить конкретный класс или тест

```bash
# Только класс
pytest tests/unit/test_validation.py::TestRepeatSpam -v

# Только один тест
pytest tests/unit/test_validation.py::TestRepeatSpam::test_ten_same_chars_in_text_rejected -v
```

### Запустить тесты по ключевому слову в названии

```bash
# Все тесты со словом "rating" в имени
pytest -k "rating" -v

# Все тесты про 422
pytest -k "422" -v

# Все тесты про удаление
pytest -k "delete" -v
```

### Показать статистику покрытия (если установлен pytest-cov)

```bash
pip install pytest-cov
pytest --cov=app --cov-report=term-missing
```

Покажет какие строки в `app/` не покрыты тестами.

### Запустить в тихом режиме (только итог)

```bash
pytest -q
```

### Остановиться при первом упавшем тесте

```bash
pytest -x
```

### Показать 10 самых медленных тестов

```bash
pytest --durations=10
```

---

## 7. Что делать если тест упал

### `ModuleNotFoundError: No module named 'app'`

Убедись что запускаешь pytest **из директории `docker-practice/`**, а не из корня репозитория:

```bash
cd docker-practice
pytest
```

### `ModuleNotFoundError: No module named 'httpx'`

```bash
pip install -r requirements-test.txt
```

### `ImportError: cannot import name 'TestClient'`

Устарела версия FastAPI или Starlette. Обнови:

```bash
pip install --upgrade fastapi starlette httpx
```

### Тесты падают с `OperationalError: no such table`

SQLite in-memory база не создала таблицы. Убедись что в `conftest.py` фикстура `engine` вызывает `Base.metadata.create_all(bind=eng)`. Если таблицы изменились в `app/models.py` — это подхватится автоматически.

### Тест с `seed_demo_data` упал

Означает что патч не сработал. Проверь что `TestClient` используется **внутри** блока `with patch("app.main.seed_demo_data")`.

### Тест сортировки нестабилен (иногда падает, иногда нет)

Значит два отзыва получили одинаковый `created_at`. В `TestGetReviews` в `test_crud.py` timestamps выставляются явно через `r.created_at = base + timedelta(hours=i)` — убедись что эта часть в `seed` fixture не была случайно удалена.

### Тест с `client + approved_review` не видит данных

Означает что фикстуры используют разные `db`-сессии. Убедись что в `conftest.py` обе фикстуры (`client` и `approved_review`) принимают один и тот же аргумент `db` — тогда pytest автоматически передаст им одну и ту же инстанцию.
