import os
import yadisk
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("YANDEX_DISK_TOKEN")
y = yadisk.YaDisk(token=token)

print(f"Токен: {token[:10]}...")

# Проверяем, работает ли токен
if y.check_token():
    print("✅ Токен валидный")

    # Проверяем, есть ли доступ к информации о диске
    try:
        info = y.get_disk_info()
        print(f"✅ Есть доступ к информации о диске")
        print(f"   Всего места: {info['total_space'] / 1024 ** 3:.2f} ГБ")
        print(f"   Свободно: {info['free_space'] / 1024 ** 3:.2f} ГБ")
    except Exception as e:
        print(f"❌ Нет доступа к информации о диске: {e}")

    # Проверяем, можно ли создать папку
    try:
        y.mkdir("/BookTracker_test")
        print("✅ Есть права на создание папки")
        y.remove("/BookTracker_test")
    except Exception as e:
        print(f"❌ Нет прав на запись: {e}")
else:
    print("❌ Токен невалидный")