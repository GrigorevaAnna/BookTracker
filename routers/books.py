from fastapi import APIRouter
from typing import List
from models.pydantic_models import BookWithProgress, BookStatus, Book, UserBook
from database.fake_db import books_db, user_books_db

router = APIRouter(prefix="/api", tags=["books"])


# Эндпоинт для получения книг пользователя
@router.get("/user/{user_id}/books", response_model=List[BookWithProgress])
def get_user_books(
        user_id: str,
        status: BookStatus | None = None
):
    result = []
    for (uid, book_id), user_book in user_books_db.items():
        if uid != user_id:
            continue

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


# Эндпоинт для добавления книги (если есть)
@router.post("/user/{user_id}/add_book")
def add_book(user_id: str, book: Book):
    # Здесь логика добавления книги
    return {"message": "Книга добавлена", "book": book}