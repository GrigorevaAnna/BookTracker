import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import time

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL не найден в переменных окружения!")

# Критически важные параметры для Render
connect_args = {
    "sslmode": "require",
    "connect_timeout": 10,
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 5,
    "options": "-c statement_timeout=30000"  # Таймаут на выполнение запроса
}

# Создаём движок с правильными настройками
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,        # Проверка соединения перед использованием
    pool_recycle=300,           # Переподключение каждые 5 минут
    pool_size=5,
    max_overflow=10,
    echo=True                   # Оставляем True для отладки, потом можно убрать
)

# Проверяем подключение при старте с повторными попытками
def init_db():
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with engine.connect() as conn:
                print(f"✅ Подключение к БД успешно (попытка {attempt + 1})")
                return
        except Exception as e:
            print(f"⚠️ Попытка {attempt + 1} не удалась: {e}")
            if attempt < max_retries - 1:
                print(f"🔄 Повтор через 3 секунды...")
                time.sleep(3)
            else:
                print("❌ Не удалось подключиться к БД после всех попыток")
                raise

# Вызываем проверку при импорте
init_db()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()