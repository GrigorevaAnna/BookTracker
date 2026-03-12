import os
import yadisk
import requests
from fastapi import UploadFile, HTTPException
import uuid
import tempfile
import shutil
from pathlib import Path

YANDEX_DISK_TOKEN = os.getenv("YANDEX_DISK_TOKEN")
YANDEX_DISK_FOLDER = "/BookTracker/covers/"


async def upload_cover_to_yandex_disk(file: UploadFile, book_id: str) -> str:
    print(f"🚀 Загрузка для книги {book_id}, файл: {file.filename}")
    print(f"📁 Content-Type: {file.content_type}")

    if not YANDEX_DISK_TOKEN:
        raise HTTPException(status_code=500, detail="Токен Яндекс.Диска не настроен")

    # Создаем клиент
    y = yadisk.YaDisk(token=YANDEX_DISK_TOKEN)

    # Проверяем токен
    if not y.check_token():
        raise HTTPException(status_code=500, detail="Токен невалидный")
    print("✅ Токен валидный")

    # Проверяем папку
    if not y.exists(YANDEX_DISK_FOLDER):
        raise HTTPException(
            status_code=500,
            detail=f"Папка {YANDEX_DISK_FOLDER} не существует. Создайте её вручную на Яндекс.Диске"
        )
    print(f"✅ Папка {YANDEX_DISK_FOLDER} существует")

    # Генерируем уникальное имя файла
    file_extension = Path(file.filename).suffix.lower()
    unique_filename = f"{book_id}_{uuid.uuid4()}{file_extension}"
    disk_file_path = f"{YANDEX_DISK_FOLDER}{unique_filename}"

    # Создаем временный файл
    temp_file_path = None
    try:
        # Сохраняем загруженный файл во временную папку
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_file_path = temp_file.name
            print(f"📁 Временный файл: {temp_file_path}")

        # Загружаем на Яндекс.Диск
        print(f"⬆️ Загружаем в: {disk_file_path}")
        y.upload(temp_file_path, disk_file_path, overwrite=True)
        print("✅ Файл загружен на Яндекс.Диск")

        # Делаем файл публичным
        print("🔓 Делаем файл публичным...")
        y.publish(disk_file_path)
        print("✅ Файл опубликован")

        # ============================================
        # ПОЛУЧАЕМ ПРАВИЛЬНУЮ ПРЯМУЮ ССЫЛКУ ЧЕРЕЗ API
        # ============================================

        # 1. Получаем публичную ссылку на файл (вида https://yadi.sk/d/...)
        file_info = y.get_meta(disk_file_path)

        # Извлекаем public_url из метаданных
        if hasattr(file_info, 'public_url'):
            public_link = file_info.public_url
        elif hasattr(file_info, 'public_key'):
            # Если нет public_url, формируем из public_key
            public_link = f"https://yadi.sk/d/{file_info.public_key}"
        else:
            # Пробуем получить через атрибуты
            public_key = getattr(file_info, 'public_key', None)
            if public_key:
                public_link = f"https://yadi.sk/d/{public_key}"
            else:
                raise Exception("Не удалось получить публичную ссылку на файл")

        print(f"🔗 Публичная ссылка на страницу: {public_link}")

        # 2. Используем REST API Яндекс.Диска для получения прямой ссылки на скачивание
        api_url = "https://cloud-api.yandex.net/v1/disk/public/resources/download"
        params = {"public_key": public_link}

        try:
            # Делаем запрос к API
            response = requests.get(api_url, params=params, timeout=10)
            response.raise_for_status()  # Проверяем на ошибки HTTP

            download_data = response.json()

            # Извлекаем прямую ссылку на скачивание
            if 'href' in download_data:
                direct_download_url = download_data['href']
                print(f"✅ Прямая ссылка на скачивание получена через API")
                print(f"🔗 {direct_download_url[:100]}...")

                # Возвращаем прямую ссылку
                return direct_download_url
            else:
                raise Exception("В ответе API нет поля 'href'")

        except requests.exceptions.RequestException as e:
            print(f"❌ Ошибка при запросе к API Яндекс.Диска: {e}")

            # Запасной вариант - формируем ссылку на предпросмотр (может работать не всегда)
            if 'public_key' in locals() or 'public_key' in dir():
                fallback_url = f"https://downloader.disk.yandex.ru/preview/{public_key}?size=2048x2048"
                print(f"⚠️ Использую запасную ссылку: {fallback_url}")
                return fallback_url
            else:
                raise HTTPException(status_code=500, detail="Не удалось получить ссылку на файл")

    except yadisk.exceptions.PathNotFoundError:
        print("❌ Путь не найден")
        raise HTTPException(status_code=500, detail="Ошибка пути на Яндекс.Диске")
    except yadisk.exceptions.ForbiddenError:
        print("❌ Нет прав на запись")
        raise HTTPException(status_code=500, detail="Нет прав на запись на Яндекс.Диск")
    except Exception as e:
        print(f"❌ Ошибка при загрузке: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки: {str(e)}")
    finally:
        # Удаляем временный файл
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
            print(f"🗑️ Временный файл удалён")