import os
import uuid
from pathlib import Path
from fastapi import UploadFile, HTTPException
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import pickle
import httpx
import tempfile

# Путь к файлу с OAuth credentials
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "oauth-credentials.json")
TOKEN_PICKLE = os.path.join(os.path.dirname(__file__), "token.pickle")

# ID папки на Google Диске (скопируйте из URL)
FOLDER_ID = "1r1tWqHZD4-sPe6ZBTbXlOcig6AMk5Swh"  # 👈 ВСТАВЬТЕ ВАШ ID

# Область доступа
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def get_authenticated_service():
    """Получение аутентифицированного сервиса через OAuth"""
    creds = None

    # Загружаем сохранённый токен
    if os.path.exists(TOKEN_PICKLE):
        with open(TOKEN_PICKLE, "rb") as token:
            creds = pickle.load(token)

    # Если токена нет или он недействителен
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        # Сохраняем токен
        with open(TOKEN_PICKLE, "wb") as token:
            pickle.dump(creds, token)

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

        # Прямая ссылка на файл
        direct_link = f"https://drive.google.com/uc?export=view&id={file_id}"

        return direct_link

    except Exception as e:
        print(f"Ошибка при загрузке на Google Drive: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки: {str(e)}")


async def download_and_upload_cover(book_id: str, cover_url: str) -> str:
    """
    Скачивает обложку по URL и загружает на Google Drive
    Возвращает прямую ссылку на Google Drive
    """
    if not cover_url:
        return ""

    print(f"📥 Скачиваю обложку для книги {book_id}: {cover_url[:80]}...")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
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

            # Создаём UploadFile напрямую из байтов
            from io import BytesIO
            file_obj = BytesIO(content)

            # Создаём объект, похожий на UploadFile
            class FakeUploadFile:
                def __init__(self, filename, content, content_type):
                    self.filename = filename
                    self.file = BytesIO(content)
                    self.content_type = content_type

                async def read(self):
                    return self.file.getvalue()

            upload_file = FakeUploadFile(f"{book_id}.{ext}", content, content_type)

            # Загружаем на Google Drive
            new_cover_url = await upload_cover_to_google_drive(upload_file, book_id)
            print(f"✅ Обложка загружена на Google Drive: {new_cover_url[:80]}...")
            return new_cover_url

    except Exception as e:
        print(f"❌ Ошибка при сохранении обложки на Google Drive: {e}")
        import traceback
        traceback.print_exc()
        return cover_url