import os
import yadisk
import requests
from fastapi import UploadFile, HTTPException
import uuid
import tempfile
import shutil
from pathlib import Path
import base64

YANDEX_DISK_TOKEN = os.getenv("YANDEX_DISK_TOKEN")
YANDEX_DISK_FOLDER = "/BookTracker/covers/"


async def upload_cover_to_yandex_disk_and_db(file: UploadFile, book_id: str, db) -> dict:
    """
    Загружает обложку на Яндекс.Диск и сохраняет в базу данных
    Возвращает словарь с ссылкой и информацией о файле
    """
    print(f"🚀 Загрузка для книги {book_id}, файл: {file.filename}")

    if not YANDEX_DISK_TOKEN:
        raise HTTPException(status_code=500, detail="Токен Яндекс.Диска не настроен")

    # Читаем содержимое файла
    file_content = await file.read()
    file_extension = Path(file.filename).suffix.lower()
    content_type = file.content_type or "image/jpeg"

    # ============================================
    # 1. СОХРАНЯЕМ В БАЗУ ДАННЫХ
    # ============================================
    from models.sql_models import Книги

    book = db.query(Книги).filter(Книги.id_книги == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    # Сохраняем бинарные данные в БД
    book.Фото_данные = file_content
    book.Фото_тип = content_type
    db.commit()
    print("✅ Обложка сохранена в базу данных")

    # ============================================
    # 2. СОХРАНЯЕМ НА ЯНДЕКС.ДИСК (опционально)
    # ============================================
    cover_url = None
    try:
        y = yadisk.YaDisk(token=YANDEX_DISK_TOKEN)

        if not y.check_token():
            print("⚠️ Токен невалидный, Яндекс.Диск не используется")
        else:
            # Проверяем папку
            if not y.exists(YANDEX_DISK_FOLDER):
                print(f"⚠️ Папка {YANDEX_DISK_FOLDER} не существует")
            else:
                # Генерируем имя файла
                unique_filename = f"{book_id}_{uuid.uuid4()}{file_extension}"
                disk_file_path = f"{YANDEX_DISK_FOLDER}{unique_filename}"

                # Сохраняем во временный файл
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
                    temp_file.write(file_content)
                    temp_file_path = temp_file.name

                # Загружаем на Яндекс.Диск
                y.upload(temp_file_path, disk_file_path, overwrite=True)
                print("✅ Файл загружен на Яндекс.Диск")

                # Делаем публичным
                y.publish(disk_file_path)

                # Получаем ссылку
                file_info = y.get_meta(disk_file_path)
                public_link = file_info.public_url if hasattr(file_info, 'public_url') else None

                if public_link:
                    # Получаем прямую ссылку через API
                    api_url = "https://cloud-api.yandex.net/v1/disk/public/resources/download"
                    params = {"public_key": public_link}
                    response = requests.get(api_url, params=params, timeout=10)
                    if response.status_code == 200:
                        cover_url = response.json().get('href')
                        book.Фото_обложки = cover_url
                        db.commit()
                        print(f"✅ Ссылка сохранена: {cover_url[:100]}...")

                # Удаляем временный файл
                os.unlink(temp_file_path)

    except Exception as e:
        print(f"⚠️ Ошибка при загрузке на Яндекс.Диск: {e}")
        # Не прерываем выполнение — обложка уже в БД

    return {
        "cover_url": cover_url,
        "cover_data": base64.b64encode(file_content).decode('utf-8'),
        "cover_type": content_type,
        "message": "Обложка сохранена в базу данных"
    }