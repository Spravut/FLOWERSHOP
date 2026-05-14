# Используем официальный образ Python 3.11 (slim-версия для минимального размера)
FROM python:3.11-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Устанавливаем системные зависимости для PostgreSQL
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Копируем файл с зависимостями
COPY requirements.txt .

# Устанавливаем зависимости внутри контейнера
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY . .

# Команда для запуска приложения
# В docker-compose будет переопределена для запуска миграций
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

