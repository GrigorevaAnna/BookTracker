import os
import uuid
from pathlib import Path
import io
import pickle
import tempfile
import asyncio
import httpx
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
from fastapi import UploadFile, HTTPException

# Путь к файлу с OAuth credentials
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "oauth-credentials.json")
TOKEN_PICKLE = os.path.join(os.path.dirname(__file__), "token.pickle")

# ID папки на Google Диске
FOLDER_ID = "1r1tWqHZD4-sPe6ZBTbXlOcig6AMk5Swh"

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def get_authenticated_service(force_reauth: bool = False):
    """Получение аутентифицированного сервиса через OAuth"""
    creds = None

    if force_reauth and os.path.exists(TOKEN_PICKLE):
        os.remove(TOKEN_PICKLE)
        print("🗑️ Старый токен удалён")

    if os.path.exists(TOKEN_PICKLE) and not force_reauth:
        with open(TOKEN_PICKLE, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                print("✅ Токен обновлён")
            except Exception as e:
                print(f"⚠️ Ошибка обновления токена: {e}")
                if os.path.exists(TOKEN_PICKLE):
                    os.remove(TOKEN_PICKLE)
                creds = None

        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            print("✅ Получен новый токен")

        with open(TOKEN_PICKLE, "wb") as token:
            pickle.dump(creds, token)

    # Просто возвращаем сервис с credentials
    return build("drive", "v3", credentials=creds)


async def upload_cover_to_google_drive(file: UploadFile, book_id: str) -> str:
    """
    Загружает обложку на Google Drive и возвращает прямую ссылку
    """
    try:
        service = get_authenticated_service()

        file_extension = Path(file.filename).suffix.lower()
        unique_filename = f"{book_id}_{uuid.uuid4()}{file_extension}"

        file_content = await file.read()

        media = MediaIoBaseUpload(
            io.BytesIO(file_content),
            mimetype=file.content_type or "image/jpeg",
            resumable=True
        )

        file_metadata = {
            "name": unique_filename,
            "parents": [FOLDER_ID]
        }

        uploaded_file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id"
        ).execute()

        file_id = uploaded_file.get("id")

        # Делаем файл публичным
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"}
        ).execute()

        direct_link = f"https://drive.google.com/uc?export=view&id={file_id}"
        print(f"✅ Файл загружен на Google Drive: {direct_link[:80]}...")

        return direct_link

    except Exception as e:
        print(f"❌ Ошибка загрузки на Google Drive: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки: {str(e)}")


async def download_and_upload_cover(book_id: str, cover_url: str) -> str:
    """
    Скачивает обложку по URL и загружает на Google Drive
    """
    if not cover_url:
        return ""

    print(f"📥 Скачиваю обложку для книги {book_id}: {cover_url[:80]}...")

    max_retries = 3
    for attempt in range(max_retries):
        tmp_path = None
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(cover_url)
                if response.status_code != 200:
                    print(f"❌ Не удалось скачать: статус {response.status_code}")
                    return cover_url

                content = response.content
                content_type = response.headers.get("content-type", "image/jpeg")

                # Определяем расширение
                ext = "jpg"
                if "png" in content_type:
                    ext = "png"
                elif "gif" in content_type:
                    ext = "gif"
                elif "webp" in content_type:
                    ext = "webp"

                # Создаём временный файл и сразу закрываем его
                import tempfile
                fd, tmp_path = tempfile.mkstemp(suffix=f".{ext}")
                os.close(fd)  # Закрываем файловый дескриптор

                # Записываем содержимое
                with open(tmp_path, "wb") as f:
                    f.write(content)

                print(f"📁 Временный файл: {tmp_path}")

                # Используем MediaFileUpload для загрузки
                service = get_authenticated_service()

                unique_filename = f"{book_id}_{uuid.uuid4()}{ext}"

                file_metadata = {
                    "name": unique_filename,
                    "parents": [FOLDER_ID]
                }

                media = MediaFileUpload(tmp_path, mimetype=content_type, resumable=True)

                uploaded_file = service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields="id"
                ).execute()

                file_id = uploaded_file.get("id")

                # Делаем файл публичным
                service.permissions().create(
                    fileId=file_id,
                    body={"type": "anyone", "role": "reader"}
                ).execute()

                # Закрываем и удаляем временный файл
                try:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                        print(f"🗑️ Временный файл удалён: {tmp_path}")
                except Exception as e:
                    print(f"⚠️ Не удалось удалить временный файл: {e}")

                direct_link = f"https://drive.google.com/uc?export=view&id={file_id}"
                print(f"✅ Обложка загружена на Google Drive: {direct_link[:80]}...")
                return direct_link

        except Exception as e:
            print(f"❌ Попытка {attempt + 1} не удалась: {e}")
            # Пытаемся удалить временный файл в случае ошибки
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except:
                    pass
            if attempt < max_retries - 1:
                print("🔄 Ждём 2 секунды и повторяем...")
                await asyncio.sleep(2)
            else:
                print("❌ Все попытки не удались, возвращаем исходную ссылку")
                return cover_url

    return cover_url