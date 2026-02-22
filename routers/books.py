from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from models.pydantic_models import BookWithProgress, BookStatus, Book, UserBook
from models.sql_models import BookDB, UserBookDB, UserDB
from database.database import get_db

router = APIRouter(prefix="/api", tags=["books"])


@router.get("/user/{user_id}/books", response_model=List[BookWithProgress])
def get_user_books(
        user_id: str,
        status: Optional[BookStatus] = None,
        db: Session = Depends(get_db)
):
    """Получить все книги пользователя с фильтром по статусу"""

    # Проверяем существует ли пользователь
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        # Если пользователя нет, возвращаем пустой список
        return []

    # Базовый запрос
    query = db.query(UserBookDB).filter(UserBookDB.user_id == user_id)

    # Фильтр по статусу если указан
    if status:
        query = query.filter(UserBookDB.status == status.value)

    user_books = query.all()

    result = []
    for ub in user_books:
        book = db.query(BookDB).filter(BookDB.id == ub.book_id).first()
        if not book:
            continue

        # Преобразуем BookDB в Book
        book_pydantic = Book(
            id=book.id,
            title=book.title,
            author=book.author,
            coverUrl=book.cover_url,
            description=book.description,
            pages=book.pages,
            genre=book.genre,
            isbn=book.isbn,
            publishedDate=book.published_date,
            publisher=book.publisher
        )

        # Преобразуем UserBookDB в UserBook
        user_book_pydantic = UserBook(
            userId=ub.user_id,
            bookId=ub.book_id,
            status=BookStatus(ub.status),
            currentPage=ub.current_page,
            rating=ub.rating,
            review=ub.review,
            startDate=ub.start_date,
            endDate=ub.end_date,
            addedDate=ub.added_date,
            readingTimeMinutes=ub.reading_time_minutes
        )

        # Вычисляем прогресс
        progress = round(ub.current_page / book.pages, 3) if book.pages > 0 else 0.0

        result.append(BookWithProgress(
            book=book_pydantic,
            userBook=user_book_pydantic,
            progress=progress
        ))

    return result


@router.get("/books", response_model=List[Book])
def get_all_books(
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(get_db)
):
    """Получить все книги (для поиска/каталога)"""
    books = db.query(BookDB).offset(skip).limit(limit).all()

    return [
        Book(
            id=book.id,
            title=book.title,
            author=book.author,
            coverUrl=book.cover_url,
            description=book.description,
            pages=book.pages,
            genre=book.genre,
            isbn=book.isbn,
            publishedDate=book.published_date,
            publisher=book.publisher
        ) for book in books
    ]


@router.get("/books/{book_id}", response_model=Book)
def get_book(
        book_id: str,
        db: Session = Depends(get_db)
):
    """Получить конкретную книгу по ID"""
    book = db.query(BookDB).filter(BookDB.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    return Book(
        id=book.id,
        title=book.title,
        author=book.author,
        coverUrl=book.cover_url,
        description=book.description,
        pages=book.pages,
        genre=book.genre,
        isbn=book.isbn,
        publishedDate=book.published_date,
        publisher=book.publisher
    )