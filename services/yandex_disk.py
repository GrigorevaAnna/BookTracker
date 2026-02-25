import os
import yadisk
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
            # Копируем содержимое из UploadFile во временный файл
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

        # Получаем публичную ссылку (правильный метод)
        # В некоторых версиях библиотеки метод называется get_public_link, в других - get_public_url
        try:
            # Пробуем первый вариант
            public_link = y.get_public_link(disk_file_path)
        except AttributeError:
            try:
                # Пробуем второй вариант
                public_link = y.get_public_url(disk_file_path)
            except AttributeError:
                # Если оба не работают, формируем ссылку вручную
                # Получаем информацию о файле
                file_info = y.get_meta(disk_file_path)
                if hasattr(file_info, 'public_url'):
                    public_link = file_info.public_url
                else:
                    # Последний вариант - берем из атрибутов
                    public_link = f"https://disk.yandex.ru/d/{file_info.public_key}"

        print(f"🔗 Публичная ссылка: {public_link}")

        return public_link

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