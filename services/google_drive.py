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