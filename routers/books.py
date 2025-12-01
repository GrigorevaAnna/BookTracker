from fastapi import APIRouter
from typing import List
from models.pydantic_models import BookWithProgress, BookStatus
from database.fake_db import books_db, user_books_db

router = APIRouter(prefix="/api", tags=["books"])


# Новый эндпоинт: все книги (с фильтром по статусу или "ALL")
@router.get("/user/{user_id}/books", response_model=List[BookWithProgress])
def get_user_books(
        user_id: str,
        status: BookStatus | None = None  # Если None — возвращаем ВСЁ
):
    result = []
    for (uid, book_id), user_book in user_books_db.items():
        if uid != user_id:
            continue

        # Фильтр по статусу (если передан)
        if status is not None and user_book.status != status:
            continue

        book = books_db.get(book_id)
        if not book:
            continue

        progress = round(user_book.currentPage / book.pages, 3) if book.pages > 0 else 0.0
        result.append(BookWithProgress(
            book=book,
            userBook=user_book,
            progress=progress
        ))
    return result