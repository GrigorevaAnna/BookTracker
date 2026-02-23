from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime

from models.pydantic_models import (
    ApiBookWithProgress, KotlinBook, KotlinUserBook,
    BookStatus, status_from_db, status_to_db
)
from models.sql_models import (
    Книги, Авторы, Произведения, Труд, Содержание,
    Аккаунты, Сессия_статус, Вишлист
)
from database.database import get_db

router = APIRouter(prefix="/api", tags=["books"])


@router.get("/user/{user_id}/books", response_model=List[ApiBookWithProgress])
def get_user_books(
        user_id: str,
        status: Optional[BookStatus] = None,
        db: Session = Depends(get_db)
):
    """
    Получить все книги пользователя с фильтром по статусу
    - Без status: все книги пользователя
    - С status=READING: только читаемые
    - С status=WANT_TO_READ: только вишлист
    - С status=FINISHED: только прочитанные
    """
    # Проверяем существует ли пользователь
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        return []

    # Базовый запрос статусов пользователя
    query = db.query(Сессия_статус).filter(Сессия_статус.id_пользователя == user_id)

    # Фильтр по статусу если указан
    if status:
        db_status = status_to_db(status)
        query = query.filter(Сессия_статус.Статус == db_status)

    user_statuses = query.all()

    result = []
    for us in user_statuses:
        # Получаем произведение
        произведение = db.query(Произведения).filter(
            Произведения.id_произведения == us.id_произведения
        ).first()

        if not произведение:
            continue

        # Получаем книгу через содержание
        содержание = db.query(Содержание).filter(
            Содержание.id_произведения == произведение.id_произведения
        ).first()

        if not содержание:
            continue

        книга = db.query(Книги).filter(Книги.id_книги == содержание.id_книги).first()

        if not книга:
            continue

        # Получаем авторов для книги
        авторы_список = []
        труд = db.query(Труд).filter(Труд.id_произведения == произведение.id_произведения).all()
        for t in труд:
            автор = db.query(Авторы).filter(Авторы.id_автора == t.id_автора).first()
            if автор:
                автор_name = f"{автор.Имя} {автор.Фамилия or ''}".strip()
                авторы_список.append(автор_name)

        # Конвертируем в Kotlin модели
        kotlin_book = KotlinBook(
            id=книга.id_книги,
            title=книга.Название,
            author=", ".join(авторы_список) if авторы_список else книга.Автор,
            coverUrl=книга.Фото_обложки or "",
            description=книга.Описание or "",
            pages=книга.Количество_страниц,
            genre=книга.Жанр or "",
            isbn=книга.ISBN or "",
            publishedDate=книга.год_издания or "",
            publisher=книга.издательство or ""
        )

        kotlin_user_book = KotlinUserBook(
            userId=us.id_пользователя,
            bookId=книга.id_книги,
            status=status_from_db(us.Статус),
            currentPage=us.current_page,
            rating=us.Рейтинг or 0.0,
            review=us.review or "",
            startDate=us.start_date or "",
            endDate=us.end_date or "",
            addedDate=us.added_date or "",
            readingTimeMinutes=us.reading_time_minutes or 0
        )

        # Вычисляем прогресс
        progress = round(us.current_page / книга.Количество_страниц, 3) if книга.Количество_страниц > 0 else 0.0

        result.append(ApiBookWithProgress(
            book=kotlin_book,
            userBook=kotlin_user_book,
            progress=progress
        ))

    return result


@router.get("/books", response_model=List[KotlinBook])
def get_all_books(
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(get_db)
):
    """Получить все книги (для поиска/каталога)"""
    книги = db.query(Книги).offset(skip).limit(limit).all()

    result = []
    for книга in книги:
        # Получаем авторов для книги
        авторы_список = []

        # Ищем авторов через цепочку связей
        содержание = db.query(Содержание).filter(
            Содержание.id_книги == книга.id_книги
        ).all()

        for с in содержание:
            труд = db.query(Труд).filter(
                Труд.id_произведения == с.id_произведения
            ).all()
            for t in труд:
                автор = db.query(Авторы).filter(
                    Авторы.id_автора == t.id_автора
                ).first()
                if автор:
                    автор_name = f"{автор.Имя} {автор.Фамилия or ''}".strip()
                    авторы_список.append(автор_name)

        kotlin_book = KotlinBook(
            id=книга.id_книги,
            title=книга.Название,
            author=", ".join(авторы_список) if авторы_список else книга.Автор,
            coverUrl=книга.Фото_обложки or "",
            description=книга.Описание or "",
            pages=книга.Количество_страниц,
            genre=книга.Жанр or "",
            isbn=книга.ISBN or "",
            publishedDate=книга.год_издания or "",
            publisher=книга.издательство or ""
        )
        result.append(kotlin_book)

    return result


@router.get("/books/{book_id}", response_model=KotlinBook)
def get_book(
        book_id: str,
        db: Session = Depends(get_db)
):
    """Получить конкретную книгу по ID"""
    книга = db.query(Книги).filter(Книги.id_книги == book_id).first()
    if not книга:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    # Получаем авторов для книги
    авторы_список = []

    содержание = db.query(Содержание).filter(
        Содержание.id_книги == книга.id_книги
    ).all()

    for с in содержание:
        труд = db.query(Труд).filter(
            Труд.id_произведения == с.id_произведения
        ).all()
        for t in труд:
            автор = db.query(Авторы).filter(
                Авторы.id_автора == t.id_автора
            ).first()
            if автор:
                автор_name = f"{автор.Имя} {автор.Фамилия or ''}".strip()
                авторы_список.append(автор_name)

    return KotlinBook(
        id=книга.id_книги,
        title=книга.Название,
        author=", ".join(авторы_список) if авторы_список else книга.Автор,
        coverUrl=книга.Фото_обложки or "",
        description=книга.Описание or "",
        pages=книга.Количество_страниц,
        genre=книга.Жанр or "",
        isbn=книга.ISBN or "",
        publishedDate=книга.год_издания or "",
        publisher=книга.издательство or ""
    )


@router.get("/user/{user_id}/wishlist", response_model=List[ApiBookWithProgress])
def get_user_wishlist(
        user_id: str,
        db: Session = Depends(get_db)
):
    """Получить только книги из вишлиста пользователя"""
    return get_user_books(user_id, BookStatus.WANT_TO_READ, db)


@router.get("/user/{user_id}/reading", response_model=List[ApiBookWithProgress])
def get_user_reading(
        user_id: str,
        db: Session = Depends(get_db)
):
    """Получить только книги, которые пользователь сейчас читает"""
    return get_user_books(user_id, BookStatus.READING, db)


@router.get("/user/{user_id}/finished", response_model=List[ApiBookWithProgress])
def get_user_finished(
        user_id: str,
        db: Session = Depends(get_db)
):
    """Получить только прочитанные книги"""
    return get_user_books(user_id, BookStatus.FINISHED, db)


@router.post("/user/{user_id}/book/{book_id}/add-to-wishlist")
def add_book_to_wishlist(
        user_id: str,
        book_id: str,
        db: Session = Depends(get_db)
):
    """Добавить книгу в вишлист пользователя"""
    # Проверяем пользователя
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Проверяем книгу
    книга = db.query(Книги).filter(Книги.id_книги == book_id).first()
    if not книга:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    # Получаем произведение для книги
    содержание = db.query(Содержание).filter(
        Содержание.id_книги == book_id
    ).first()

    if not содержание:
        raise HTTPException(status_code=404, detail="Произведение не найдено")

    # Проверяем, нет ли уже в вишлисте
    existing = db.query(Сессия_статус).filter(
        and_(
            Сессия_статус.id_пользователя == user_id,
            Сессия_статус.id_произведения == содержание.id_произведения
        )
    ).first()

    if existing:
        if existing.Статус == "Хочу прочитать":
            return {"message": "Книга уже в вишлисте"}
        else:
            # Обновляем статус на вишлист
            existing.Статус = "Хочу прочитать"
            existing.updated_at = datetime.now()
    else:
        # Создаем новую запись
        new_status = Сессия_статус(
            id_пользователя=user_id,
            id_произведения=содержание.id_произведения,
            Статус="Хочу прочитать",
            current_page=0,
            added_date=datetime.now().isoformat()
        )
        db.add(new_status)

    # Также добавляем в вишлист
    wishlist_item = Вишлист(
        id_пользователя=user_id,
        id_книги=book_id,
        дата_добавления=datetime.now().isoformat(),
        приоритет=1
    )
    db.add(wishlist_item)

    db.commit()

    return {"message": "Книга добавлена в вишлист"}