# Base image
FROM python:3.11-slim

# Workdir inside container
WORKDIR /app

# Copy dependencies first for better layer caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source (compose can override with a bind mount for dev)
COPY . .

# Default command (can be overridden by docker-compose)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
