# Base image
FROM python:3.11-slim

# Workdir inside container
WORKDIR /app

# Copy dependencies first for better layer caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# During development the source code is mounted via bind mount.
# For production you can uncomment the next line.
# COPY . .

# Default command (can be overridden by docker-compose)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
