#!/usr/bin/env python
"""Скрипт для запуска сервера с обработкой ошибок"""
import sys
import os

# Добавляем текущую директорию в путь
sys.path.insert(0, os.path.dirname(__file__))

try:
    import uvicorn
    from app.main import app
    
    print("Starting server...")
    print("API will be available at: http://127.0.0.1:8000")
    print("Swagger UI: http://127.0.0.1:8000/docs")
    print("Press CTRL+C to stop")
    
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )
except KeyboardInterrupt:
    print("\nServer stopped")
except Exception as e:
    print(f"Error starting server: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

