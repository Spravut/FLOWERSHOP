"""Скрипт для создания базы данных"""
import pg8000

try:
    # Подключаемся к postgres БД для создания новой БД
    conn = pg8000.connect(
        user="postgres",
        password="StrongPassword123!",
        host="localhost",
        port=5432,
        database="postgres"  # Подключаемся к системной БД
    )
    
    conn.autocommit = True
    cursor = conn.cursor()
    
    # Проверяем, существует ли база
    cursor.execute("SELECT 1 FROM pg_database WHERE datname = 'notifications_db'")
    exists = cursor.fetchone()
    
    if not exists:
        cursor.execute("CREATE DATABASE notifications_db")
        print("✅ База данных 'notifications_db' создана успешно!")
    else:
        print("ℹ️ База данных 'notifications_db' уже существует")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Ошибка при создании БД: {e}")
    print("\nПопробуйте создать БД вручную:")
    print("docker exec -it flowershop-db psql -U postgres -c 'CREATE DATABASE notifications_db;'")

