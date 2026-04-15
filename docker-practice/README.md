# Docker Practice — Reviews Service

Микросервис отзывов и рейтингов для Fleur de Reve (FastAPI + PostgreSQL). Ниже — построчное объяснение каждого файла и как всё связано.

---

## Содержание

1. [Корень проекта](#корень-проекта)
2. [Приложение (app/)](#приложение-app)
3. [Docker и окружение](#docker-и-окружение)
4. [Alembic (миграции)](#alembic-миграции)
5. [Как всё работает вместе](#как-всё-работает-вместе)

---

## Корень проекта

### main.py

```python
from app.main import app
```

| Строка | Назначение |
|--------|------------|
| 1 | Импорт объекта `app` (экземпляр FastAPI) из пакета `app`, модуль `main`. |
| 2 | Переменная `app` экспортируется наружу — по ней можно запустить сервер командой `uvicorn main:app`, не указывая `app.main:app`. Удобно для старых туториалов и скриптов. |

---

### .gitignore

```
.env
__pycache__/
*.pyc
.venv/
```

| Строка | Назначение |
|--------|------------|
| .env | Файл с паролями и секретами — не попадает в git. |
| __pycache__/ | Кэш скомпилированного Python — генерируется автоматически. |
| *.pyc | Скомпилированные .py-файлы. |
| .venv/ | Виртуальное окружение — зависимости ставить локально, в репозиторий не коммитить. |

---

### .env.example

```
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=reviews_db
DB_HOST=localhost
DB_PORT=5432
SQL_ECHO=false
```

| Строка | Назначение |
|--------|------------|
| DB_USER | Имя пользователя PostgreSQL. |
| DB_PASSWORD | Пароль пользователя БД. |
| DB_NAME | Имя базы данных. |
| DB_HOST | Хост БД: localhost при локальном запуске, в Docker Compose подставляется `db` (имя сервиса). |
| DB_PORT | Порт PostgreSQL (по умолчанию 5432). |
| SQL_ECHO | true — в консоль выводятся SQL-запросы (отладка); false — тихо. |

Копируем в `.env` и при необходимости меняем значения. `.env` не коммитится (см. .gitignore).

---

## Приложение (app/)

### app/__init__.py

Файл пустой. Нужен только чтобы Python считал каталог `app` пакетом и разрешал импорты вида `from app.database import ...`.

---

### app/database.py

| Строка | Назначение |
|--------|------------|
| 1 | `import os` — доступ к переменным окружения через `os.getenv`. |
| 3 | `load_dotenv` — подгружает переменные из файла `.env` в `os.environ`. |
| 4–5 | SQLAlchemy: `create_engine` — подключение к БД, `declarative_base` и `sessionmaker` — для моделей и сессий. |
| 7 | Вызов `load_dotenv()` при импорте модуля — дальше все `os.getenv` видят значения из `.env`. |
| 9–13 | Параметры подключения к PostgreSQL из окружения с запасными значениями по умолчанию (postgres, localhost, 5432, reviews_db). |
| 15–17 | `DATABASE_URL`: либо задаётся целиком через `DATABASE_URL`, либо собирается из DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME. Формат: `postgresql+psycopg2://user:password@host:port/dbname`. |
| 18 | `SQL_ECHO` — если в .env указано "true", то `echo=True` у движка и все SQL-запросы выводятся в консоль. |
| 20 | `create_engine` создаёт движок; `pool_pre_ping=True` — перед выдачей соединения из пула проверяется, что оно живое. |
| 21 | `SessionLocal` — фабрика сессий: каждая сессия привязана к этому движку, без автокоммита и автофлаша. |
| 22 | `Base` — базовый класс для всех моделей SQLAlchemy (от него наследуется `Review` в models.py). |
| 25–29 | `get_db()` — генератор: создаёт сессию, отдаёт её в обработчик (yield), после запроса закрывает сессию в `finally`. Используется как FastAPI dependency: `db: Session = Depends(get_db)`. |

Итог: один раз при старте приложения задаётся подключение к БД и фабрика сессий; каждый HTTP-запрос получает свою сессию через `get_db` и по завершении её закрывает.

---

### app/models.py

| Строка | Назначение |
|--------|------------|
| 1–12 | Импорты из SQLAlchemy: типы колонок (Integer, String, Text, Boolean, DateTime), ограничения (CheckConstraint, Index), `func` для now(), `text as sa_text` для server_default. |
| 14 | Базовый класс для таблиц — из database.py. |
| 17 | Класс модели таблицы отзывов. |
| 18 | Имя таблицы в PostgreSQL — `reviews`. |
| 19–25 | Ограничения уровня таблицы: рейтинг от 1 до 5; индексы по product_id, is_approved, rating, created_at — ускоряют фильтрацию и сортировку. |
| 26 | Первичный ключ, автоинкремент, индекс по id. |
| 27–28 | product_id и user_id — опциональные (отзыв может быть к товару или к магазину). |
| 29 | name — обязательная строка до 100 символов. |
| 30 | text — текст отзыва без ограничения по длине (Text). |
| 31 | rating — число от 1 до 5 (дополнительно проверяется CheckConstraint в __table_args__). |
| 32–34 | is_approved — по умолчанию false и на уровне БД (server_default), чтобы новые отзывы не светились без модерации. |
| 35 | created_at — время с таймзоной, по умолчанию now() на стороне БД. |

Модель описывает структуру таблицы; по ней Alembic строит миграции, а CRUD работает через сессию и эту модель.

---

### app/schemas.py

| Строка | Назначение |
|--------|------------|
| 1–4 | datetime для полей времени; Optional для необязательных полей; Pydantic — BaseModel, ConfigDict, Field, field_validator. |
| 7–12 | `ReviewBase`: общие поля для создания/ответа — product_id, user_id (опционально), name (обязательно), text, rating 1–5. Field(..., max_length=100) — обязательное поле с ограничением длины. |
| 14–19 | Валидатор для name и text: обрезает пробелы и не допускает пустую строку — иначе ValueError (FastAPI вернёт 422). |
| 23–24 | `ReviewCreate` — то, что приходит в POST /reviews; наследует ReviewBase, дополнений нет. |
| 27–29 | `ReviewUpdate` — для PATCH: только is_approved. extra="forbid" — запрещает лишние поля в JSON. |
| 32–41 | `ReviewResponse` — что возвращаем в ответах: все поля отзыва включая id и created_at. from_attributes=True — позволяет создавать из ORM-объекта (models.Review). |
| 44–46 | `ReviewList` — ответ GET /reviews: список items (ReviewResponse) и total (общее количество). |
| 49–52 | `RatingSummary` — ответ GET /ratings/summary: средний балл (или None), количество, опционально product_id. |
| 55–58 | `ErrorResponse` — единый формат ошибки (error, code, details); можно использовать в обработчиках. |

Схемы задают контракт API: валидацию входящих данных и форму ответов.

---

### app/crud.py

| Строка | Назначение |
|--------|------------|
| 1–6 | Optional, Tuple для типов; func — для avg(); Session — тип сессии; модели и схемы приложения. |
| 9–19 | Сигнатура get_reviews: сессия, затем только keyword-аргументы (limit, offset, фильтры, sort). Возвращает кортеж (список отзывов, общее число). |
| 20 | Базовый запрос — все записи из таблицы reviews. |
| 22–28 | По очереди применяем фильтры, если параметры заданы: approved_only, product_id, min_rating, max_rating. |
| 30–37 | Сортировка по sort: по дате (desc/asc) или по рейтингу (desc/asc). |
| 39–41 | Считаем total до limit/offset, потом берём срез и возвращаем (items, total). |
| 45–49 | create_review: из схемы ReviewCreate делаем словарь, добавляем is_approved=False, создаём модель, add, commit, refresh (чтобы подтянуть id и created_at из БД), возвращаем объект. |
| 52–53 | get_review: получение одного отзыва по id через db.get(Review, id); если нет — вернёт None. |
| 56–65 | update_review: из ReviewUpdate берём только переданные поля (exclude_unset=True), проставляем в объект, commit, refresh, возвращаем объект. |
| 68–70 | delete_review: удаление записи и commit. |
| 73–75 | Сигнатура get_rating_summary: сессия, product_id (опционально), approved_only. |
| 76–85 | Запрос по отзывам; фильтр is_approved; если product_id не передан — считаем отзывы по магазину (product_id IS NULL), иначе по конкретному товару. |
| 87–92 | Считаем количество; если 0 — возвращаем (None, 0). Иначе считаем среднее по rating через func.avg, округляем до двух знаков, возвращаем (average, count). |

CRUD не знает про HTTP — только про сессию и модели; вызывается из эндпоинтов в main.py.

---

### app/main.py

| Строка | Назначение |
|--------|------------|
| 1–7 | Импорты: типы (Literal, Optional), FastAPI (Depends, HTTPException, Query, Response, status), Session, приложение (crud, models, schemas), SessionLocal и get_db из database. |
| 9–13 | Создание приложения FastAPI с title, description, version — отображаются в /docs (Swagger). |
| 16–51 | seed_demo_data(): открывает сессию; если отзывов уже есть — выходит; иначе добавляет три демо-отзыва (add_all), commit, в finally закрывает сессию. |
| 55–57 | Обработчик события startup: при старте приложения вызывается seed_demo_data(). |
| 60–66 | GET / — приветственный JSON с сообщением, статусом и ссылкой на /docs. |
| 69–91 | GET /reviews: параметры через Query (limit, offset, approved_only, product_id, min_rating, max_rating, sort). db через Depends(get_db). Вызов crud.get_reviews, ответ — schemas.ReviewList (items + total). |
| 94–96 | POST /reviews: тело — ReviewCreate, сессия через get_db. Создание через crud.create_review, ответ 201, схема ReviewResponse. |
| 99–104 | GET /reviews/{reviewId}: по id получаем отзыв; если None — 404, иначе возвращаем ReviewResponse. |
| 107–117 | PATCH /reviews/{reviewId}: тело — ReviewUpdate. Если ничего не передано — 422. Иначе получаем отзыв, если нет — 404, иначе crud.update_review и ответ. |
| 120–126 | DELETE /reviews/{reviewId}: получаем отзыв; если нет — 404, иначе удаление через crud и ответ 204 без тела. |
| 129–138 | GET /ratings/summary: опционально product_id, approved_only по умолчанию true. crud.get_rating_summary, ответ — RatingSummary. |

Цепочка: запрос → FastAPI → get_db даёт сессию → эндпоинт вызывает crud → crud работает с models и БД → ответ формируется через schemas.

---

## Docker и окружение

### requirements.txt

```
fastapi
uvicorn
pydantic
sqlalchemy
psycopg2-binary
alembic
python-dotenv
```

| Пакет | Назначение |
|-------|------------|
| fastapi | Фреймворк API и автодокументация. |
| uvicorn | ASGI-сервер для запуска FastAPI. |
| pydantic | Встроен в FastAPI; используется в schemas для валидации. |
| sqlalchemy | ORM и работа с БД. |
| psycopg2-binary | Драйвер PostgreSQL для SQLAlchemy. |
| alembic | Миграции схемы БД. |
| python-dotenv | Загрузка .env. |

---

### Dockerfile

| Строка | Назначение |
|--------|------------|
| 2 | Базовый образ — Python 3.11 slim (меньший размер). |
| 5 | Рабочая директория внутри контейнера — /app. |
| 8 | Копируем только requirements.txt (для кэша слоёв). |
| 11 | Устанавливаем зависимости без кэша pip. |
| 14–16 | Закомментировано копирование кода — при разработке код монтируется из хоста (docker-compose volumes). Для продакшена раскомментировать COPY . . |
| 19 | Команда по умолчанию: uvicorn запускает app.main:app на 0.0.0.0:8000 с --reload. В docker-compose эта команда переопределяется (добавляется alembic upgrade). |

---

### docker-compose.yml

| Строка | Назначение |
|--------|------------|
| 1 | Версия формата (опционально в новых Compose). |
| 2 | Секция сервисов. |
| 3 | Сборка образа из текущей директории (Dockerfile). |
| 4 | Имя образа — reviews-service. |
| 5 | Имя контейнера — reviews_service_app. |
| 6–7 | Проброс порта 8000 с контейнера на хост. |
| 8–9 | Текущая директория монтируется в /app — код меняется без пересборки. |
| 10–11 | Переменные из .env. |
| 12–14 | DB_HOST=db и DB_PORT=5432 — приложение подключается к сервису db по имени. |
| 15–17 | Запуск app только после того, как db прошёл healthcheck (condition: service_healthy). |
| 18–20 | Команда: сначала alembic upgrade head (применить миграции), затем uvicorn с --reload. |
| 22–24 | Сервис БД: образ postgres:15, имя контейнера reviews_service_db. |
| 25–30 | Переменные PostgreSQL из .env (user, password, db name). |
| 31–32 | Том postgres_data на /var/lib/postgresql/data — данные сохраняются между перезапусками. |
| 33–34 | Порт 5432 наружу — можно подключаться с хоста (pgAdmin, DBeaver). |
| 35–39 | healthcheck: pg_isready раз в 5 сек, таймаут 3 сек, до 10 попыток; пока не ок — сервис app не стартует. |
| 41–42 | Именованный том postgres_data объявлен здесь и используется в db. |

Итог: один файл поднимает БД и приложение, приложение ждёт готовности БД и применяет миграции перед стартом API.

---

## Alembic (миграции)

### alembic.ini

| Строка | Назначение |
|--------|------------|
| 1–2 | [alembic] — секция конфигурации Alembic. |
| 2 | script_location = alembic — папка с env.py и versions. |
| 3 | prepend_sys_path = . — корень проекта в PYTHONPATH (чтобы работал import app). |
| 4 | sqlalchemy.url — URL по умолчанию; в реальности перезаписывается в env.py из .env. |
| 5–6 | post_write_hooks — пусто (можно добавить автоформатирование после генерации миграции). |
| 8–16 | Логгеры: root, sqlalchemy, alembic; уровни WARN/INFO. |
| 17–36 | Обработчики и форматтеры логов — вывод в stderr с уровнем и именем логгера. |

---

### alembic/env.py

| Строка | Назначение |
|--------|------------|
| 1–2 | fileConfig для логирования; os для getenv. |
| 4–6 | context — API Alembic для запуска миграций; load_dotenv; engine_from_config и pool для создания движка. |
| 8–9 | Base — метаданные таблиц; импорт models нужен, чтобы все модели (Review) были зарегистрированы в Base.metadata. |
| 11 | config — объект конфига из alembic.ini. |
| 13–14 | Если указан config_file_name — настраиваем логирование из ini. |
| 16–26 | Загружаем .env; берём DATABASE_URL или собираем из DB_* переменных. |
| 28 | Подставляем полученный database_url в config — его будет использовать Alembic. |
| 29 | target_metadata = Base.metadata — по нему Alembic видит все таблицы из models. |
| 32–42 | run_migrations_offline: для режима "alembic upgrade --sql" — генерируем SQL без подключения к БД; literal_binds и dialect_opts для корректного SQL. |
| 45–56 | run_migrations_online: создаём движок из config, подключаемся к БД, настраиваем context с connection и target_metadata, выполняем миграции в транзакции. |
| 59–62 | Если alembic в offline режиме — вызываем offline, иначе — online (реальное подключение к БД). |

Итог: при `alembic upgrade head` env.py читает .env, подключается к той же БД, что и приложение, и применяет скрипты из versions/.

---

### alembic/script.py.mako

Шаблон (Mako) для новых миграций. При команде `alembic revision` генерируется новый файл в versions/, где подставляются:

| Фрагмент | Назначение |
|----------|------------|
| ${repr(up_revision)} | ID новой ревизии. |
| ${repr(down_revision)} | ID родительской ревизии (для цепочки). |
| branch_labels, depends_on | Ветки и зависимости (обычно None). |
| ${imports if imports else ""} | Доп. импорты при автогенерации. |
| ${upgrades if upgrades else "pass"} | Код для upgrade(). |
| ${downgrades if downgrades else "pass"} | Код для downgrade(). |

В проекте одна миграция создана вручную (0001_create_reviews_table.py); следующие можно генерировать через `alembic revision --autogenerate`.

---

### alembic/versions/0001_create_reviews_table.py

| Строка | Назначение |
|--------|------------|
| 1–10 | Импорты и переменные ревизии: revision = "0001_create_reviews", down_revision = None (первая миграция), branch_labels и depends_on = None. |
| 12–33 | upgrade(): создаём таблицу reviews с колонками id, product_id, user_id, name, text, rating, is_approved (server_default false), created_at (now()), CheckConstraint для рейтинга 1–5, PrimaryKey. |
| 35–39 | Создаём индексы по id, product_id, is_approved, rating, created_at. |
| 41–47 | downgrade(): удаляем индексы в обратном порядке, затем таблицу. |

При первом `alembic upgrade head` в БД появляется таблица reviews; при downgrade она удаляется.

---

## Как всё работает вместе

1. **Запуск**: `docker compose up --build`  
   - Стартует PostgreSQL (db), затем по healthcheck — приложение (app).  
   - В app выполняется `alembic upgrade head` → создаётся/обновляется таблица reviews.  
   - Запускается uvicorn (app.main:app).

2. **Запрос**:  
   - Клиент → GET /reviews?limit=10 → uvicorn → FastAPI.  
   - FastAPI вызывает get_db() → создаётся сессия БД.  
   - Эндпоинт read_reviews вызывает crud.get_reviews(db, ...).  
   - crud строит запрос по models.Review, фильтры/сортировка/limit/offset, возвращает (items, total).  
   - Ответ сериализуется в schemas.ReviewList и уходит клиенту.  
   - get_db в finally закрывает сессию.

3. **Данные**:  
   - При первом старте on_startup вызывает seed_demo_data() — в БД добавляются три демо-отзыва, если таблица пустая.  
   - Все последующие запросы читают/пишут уже существующую таблицу.

4. **Конфиг**:  
   - .env (из .env.example) задаёт DB_* и при локальном запуске, и в Docker (через env_file и environment в docker-compose); в контейнере app переменная DB_HOST подменена на `db`, поэтому приложение подключается к контейнеру PostgreSQL.

Если нужно, можно вынести любой из блоков (например, только app/ или только Docker) в отдельный раздел с ещё более короткими пояснениями.
