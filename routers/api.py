from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import List, Optional
from datetime import datetime
import os
import uuid
import httpx

from services.book_search import combined_search
from services.google_drive import upload_cover_to_google_drive

from database.database import get_db
from models.sql_models import (
    Книги, Авторы, Произведения, Труд, Содержание,
    Аккаунты, Сессия_статус, Вишлист, Сессии, Цитаты,
    Тэги, Связь_цитаты_тэги
)
from models.pydantic_models import (
    ApiBookWithProgress, KotlinBook, KotlinUserBook, KotlinUser,
    BookStatus, status_from_db, status_to_db
)

# from services.yandex_disk import upload_cover_to_yandex_disk_and_db


router = APIRouter(prefix="/api", tags=["api"])


# ============================================
# ПОЛЬЗОВАТЕЛИ
# ============================================

@router.get("/users/{user_id}", response_model=KotlinUser, tags=["Пользователи"])
def get_user(
        user_id: str,
        db: Session = Depends(get_db)
):
    """Получить информацию о пользователе"""
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        return KotlinUser(id=user_id)
    return KotlinUser.from_db_user(user)


@router.post("/users/register", tags=["Пользователи"])
async def register_user(
        nickname: str,
        email: str,
        password: str,
        db: Session = Depends(get_db)
):
    """Регистрация нового пользователя"""
    existing = db.query(Аккаунты).filter(Аккаунты.Почта == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")

    existing_nick = db.query(Аккаунты).filter(Аккаунты.Никнейм == nickname).first()
    if existing_nick:
        raise HTTPException(status_code=400, detail="Никнейм уже занят")

    user_id = str(uuid.uuid4())[:8]
    new_user = Аккаунты(
        id_пользователя=user_id,
        Никнейм=nickname,
        Почта=email,
        Пароль=password,
        Дата_регистрации=datetime.now().isoformat(),
        reading_goal=12,
        pages_per_day_goal=50
    )
    db.add(new_user)
    db.commit()

    return {
        "user_id": user_id,
        "nickname": nickname,
        "email": email,
        "message": "Регистрация успешна"
    }


@router.put("/users/{user_id}/profile", tags=["Пользователи"])
async def update_user_profile(
        user_id: str,
        nickname: Optional[str] = None,
        email: Optional[str] = None,
        reading_goal: Optional[int] = None,
        pages_per_day_goal: Optional[int] = None,
        avatar: Optional[UploadFile] = None,
        db: Session = Depends(get_db)
):
    """Обновление профиля пользователя"""
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if nickname:
        user.Никнейм = nickname
    if email:
        user.Почта = email
    if reading_goal:
        user.reading_goal = reading_goal
    if pages_per_day_goal:
        user.pages_per_day_goal = pages_per_day_goal
    if avatar:
        avatar_content = await avatar.read()
        user.Фото = avatar_content

    user.updated_at = datetime.now()
    db.commit()

    return {"message": "Профиль обновлён"}


# ============================================
# БИБЛИОТЕКА
# ============================================

@router.get("/user/{user_id}/books", response_model=List[ApiBookWithProgress], tags=["Библиотека"])
def get_user_books(
        user_id: str,
        status: Optional[BookStatus] = None,
        db: Session = Depends(get_db)
):
    """Получить все книги пользователя с фильтром по статусу"""
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        return []

    query = db.query(Сессия_статус).filter(Сессия_статус.id_пользователя == user_id)
    if status:
        query = query.filter(Сессия_статус.Статус == status_to_db(status))

    user_statuses = query.all()
    result = []

    for us in user_statuses:
        произведение = db.query(Произведения).filter(
            Произведения.id_произведения == us.id_произведения
        ).first()
        if not произведение:
            continue

        содержание = db.query(Содержание).filter(
            Содержание.id_произведения == произведение.id_произведения
        ).first()
        if not содержание:
            continue

        книга = db.query(Книги).filter(Книги.id_книги == содержание.id_книги).first()
        if not книга:
            continue

        авторы_список = []
        труд = db.query(Труд).filter(Труд.id_произведения == произведение.id_произведения).all()
        for t in труд:
            автор = db.query(Авторы).filter(Авторы.id_автора == t.id_автора).first()
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

        progress = round(us.current_page / книга.Количество_страниц, 3) if книга.Количество_страниц > 0 else 0.0
        result.append(ApiBookWithProgress(book=kotlin_book, userBook=kotlin_user_book, progress=progress))

    return result


@router.get("/user/{user_id}/reading", response_model=List[ApiBookWithProgress], tags=["Библиотека"])
def get_user_reading(user_id: str, db: Session = Depends(get_db)):
    return get_user_books(user_id, BookStatus.READING, db)


@router.get("/user/{user_id}/finished", response_model=List[ApiBookWithProgress], tags=["Библиотека"])
def get_user_finished(user_id: str, db: Session = Depends(get_db)):
    return get_user_books(user_id, BookStatus.FINISHED, db)


@router.get("/user/{user_id}/stats", tags=["Библиотека"])
def get_user_stats(user_id: str, db: Session = Depends(get_db)):
    """Получить статистику чтения пользователя"""
    status_counts = db.query(
        Сессия_статус.Статус, db.func.count().label('count')
    ).filter(Сессия_статус.id_пользователя == user_id).group_by(Сессия_статус.Статус).all()

    total_time = db.query(db.func.sum(Сессия_статус.reading_time_minutes)).filter(
        Сессия_статус.id_пользователя == user_id
    ).scalar() or 0

    total_pages = db.query(db.func.sum(Сессия_статус.current_page)).filter(
        Сессия_статус.id_пользователя == user_id,
        Сессия_статус.Статус == 'Прочитано'
    ).scalar() or 0

    avg_rating = db.query(db.func.avg(Сессия_статус.Рейтинг)).filter(
        Сессия_статус.id_пользователя == user_id,
        Сессия_статус.Рейтинг > 0
    ).scalar() or 0

    stats = {
        "wishlist": 0, "reading": 0, "finished": 0, "paused": 0,
        "total_reading_time_minutes": total_time,
        "total_pages_read": total_pages,
        "average_rating": round(float(avg_rating), 1)
    }

    for status_row in status_counts:
        db_status, count = status_row
        if db_status == "Хочу прочитать":
            stats["wishlist"] = count
        elif db_status == "Читаю":
            stats["reading"] = count
        elif db_status == "Прочитано":
            stats["finished"] = count
        elif db_status == "Приостановлено":
            stats["paused"] = count

    return stats


@router.put("/user/{user_id}/book/{book_id}/status", tags=["Библиотека"])
def update_book_status(
        user_id: str,
        book_id: str,
        status: BookStatus,
        current_page: Optional[int] = None,
        rating: Optional[float] = None,
        review: Optional[str] = None,
        db: Session = Depends(get_db)
):
    содержание = db.query(Содержание).filter(Содержание.id_книги == book_id).first()
    if not содержание:
        raise HTTPException(status_code=404, detail="Произведение не найдено")

    user_status = db.query(Сессия_статус).filter(
        and_(
            Сессия_статус.id_пользователя == user_id,
            Сессия_статус.id_произведения == содержание.id_произведения
        )
    ).first()

    if user_status:
        user_status.Статус = status_to_db(status)
        if current_page is not None:
            user_status.current_page = current_page
        if rating is not None:
            user_status.Рейтинг = rating
        if review is not None:
            user_status.review = review
        if status == BookStatus.FINISHED:
            книга = db.query(Книги).filter(Книги.id_книги == book_id).first()
            if книга:
                user_status.current_page = книга.Количество_страниц
                user_status.end_date = datetime.now().isoformat()
    else:
        user_status = Сессия_статус(
            id_пользователя=user_id,
            id_произведения=содержание.id_произведения,
            Статус=status_to_db(status),
            current_page=current_page or 0,
            Рейтинг=rating,
            review=review,
            added_date=datetime.now().isoformat()
        )
        db.add(user_status)

    db.commit()
    return {"message": f"Статус обновлен на {status.value}"}


@router.put("/user/{user_id}/book/{book_id}/progress", tags=["Библиотека"])
async def update_reading_progress(
        user_id: str,
        book_id: str,
        current_page: int,
        db: Session = Depends(get_db)
):
    """Обновить текущую страницу чтения"""
    content = db.query(Содержание).filter(Содержание.id_книги == book_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    status = db.query(Сессия_статус).filter(
        and_(
            Сессия_статус.id_пользователя == user_id,
            Сессия_статус.id_произведения == content.id_произведения
        )
    ).first()

    if not status:
        raise HTTPException(status_code=404, detail="Книга не найдена в библиотеке")

    book = db.query(Книги).filter(Книги.id_книги == book_id).first()
    if book and current_page > book.Количество_страниц:
        current_page = book.Количество_страниц

    status.current_page = current_page
    status.updated_at = datetime.now()

    if book and current_page >= book.Количество_страниц:
        status.Статус = "Прочитано"
        status.end_date = datetime.now().isoformat()

    db.commit()

    progress = round(current_page / book.Количество_страниц, 3) if book and book.Количество_страниц > 0 else 0

    return {
        "message": "Прогресс обновлён",
        "current_page": current_page,
        "progress": progress,
        "status": status.Статус
    }


@router.post("/user/{user_id}/reading-session", tags=["Библиотека"])
async def add_reading_session(
        user_id: str,
        book_id: str,
        start_page: int,
        end_page: int,
        duration_minutes: int,
        quote_text: Optional[str] = None,
        quote_page: Optional[int] = None,
        db: Session = Depends(get_db)
):
    """Добавляет сессию чтения и обновляет прогресс"""
    book = db.query(Книги).filter(Книги.id_книги == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    content = db.query(Содержание).filter(Содержание.id_книги == book_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="Произведение не найдено")

    status = db.query(Сессия_статус).filter(
        and_(
            Сессия_статус.id_пользователя == user_id,
            Сессия_статус.id_произведения == content.id_произведения
        )
    ).first()

    if not status:
        raise HTTPException(status_code=404, detail="Книга не найдена в библиотеке")

    session_id = str(uuid.uuid4())[:8]
    pages_read = end_page - start_page

    new_session = Сессии(
        id_сессии=session_id,
        id_пользователя=user_id,
        id_книги=book_id,
        Начальная_страница=start_page,
        Последняя_страница=end_page,
        pages_read=pages_read,
        duration_minutes=duration_minutes,
        Дата_начала=datetime.now().isoformat()
    )
    db.add(new_session)

    status.current_page = end_page
    status.reading_time_minutes = (status.reading_time_minutes or 0) + duration_minutes
    status.updated_at = datetime.now()

    if end_page >= book.Количество_страниц:
        status.Статус = "Прочитано"
        status.end_date = datetime.now().isoformat()

    quote_id = None
    if quote_text:
        quote_id = str(uuid.uuid4())[:8]
        new_quote = Цитаты(
            id_цитаты=quote_id,
            id_пользователя=user_id,
            id_произведения=content.id_произведения,
            Текст=quote_text,
            Страница=quote_page or end_page,
            Дата=datetime.now().isoformat()
        )
        db.add(new_quote)

    db.commit()

    progress = round(end_page / book.Количество_страниц, 3) if book.Количество_страниц > 0 else 0

    return {
        "message": "Сессия чтения добавлена",
        "session_id": session_id,
        "pages_read": pages_read,
        "duration_minutes": duration_minutes,
        "current_page": end_page,
        "progress": progress,
        "status": status.Статус,
        "quote_added": quote_id is not None,
        "quote_id": quote_id
    }


@router.put("/user/{user_id}/book/{book_id}/review", tags=["Библиотека"])
async def add_review(
        user_id: str,
        book_id: str,
        rating: float,
        review: Optional[str] = None,
        db: Session = Depends(get_db)
):
    """Добавить отзыв и оценку на книгу"""
    content = db.query(Содержание).filter(Содержание.id_книги == book_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    status = db.query(Сессия_статус).filter(
        and_(
            Сессия_статус.id_пользователя == user_id,
            Сессия_статус.id_произведения == content.id_произведения
        )
    ).first()

    if not status:
        raise HTTPException(status_code=404, detail="Книга не найдена в библиотеке")

    if rating < 0 or rating > 5:
        raise HTTPException(status_code=400, detail="Рейтинг должен быть от 0 до 5")

    status.Рейтинг = rating
    if review:
        status.review = review
    status.updated_at = datetime.now()
    db.commit()

    return {"message": "Отзыв добавлен", "rating": rating}


@router.delete("/user/{user_id}/book/{book_id}", tags=["Библиотека"])
async def remove_book_from_user(
        user_id: str,
        book_id: str,
        db: Session = Depends(get_db)
):
    """Удаляет книгу из библиотеки пользователя"""
    content = db.query(Содержание).filter(Содержание.id_книги == book_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="Связь книги с произведением не найдена")

    user_book = db.query(Сессия_статус).filter(
        and_(
            Сессия_статус.id_пользователя == user_id,
            Сессия_статус.id_произведения == content.id_произведения
        )
    ).first()

    if not user_book:
        raise HTTPException(status_code=404, detail="Книга не найдена в библиотеке пользователя")

    old_status = user_book.Статус
    db.delete(user_book)

    wishlist_item = db.query(Вишлист).filter(
        and_(
            Вишлист.id_пользователя == user_id,
            Вишлист.id_книги == book_id
        )
    ).first()

    if wishlist_item:
        db.delete(wishlist_item)

    db.commit()

    return {
        "message": f"Книга удалена из библиотеки",
        "book_id": book_id,
        "old_status": old_status
    }


@router.post("/user/{user_id}/add-book", tags=["Библиотека"])
async def add_book_to_user(
        user_id: str,
        title: str,
        author: str,
        description: Optional[str] = None,
        genre: Optional[str] = None,
        pages: Optional[int] = None,
        isbn: Optional[str] = None,
        cover_url: Optional[str] = None,
        cover_file: Optional[UploadFile] = None,
        db: Session = Depends(get_db)
):
    """Добавляет книгу пользователю со статусом 'Хочу прочитать'"""
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    existing_book = None
    if isbn:
        existing_book = db.query(Книги).filter(Книги.ISBN == isbn).first()

    if not existing_book:
        existing_book = db.query(Книги).filter(
            and_(
                Книги.Название.ilike(title.strip()),
                Книги.Автор.ilike(author.strip())
            )
        ).first()

    if not existing_book:
        book_id = str(uuid.uuid4())[:8]
        work_id = str(uuid.uuid4())[:8]

        new_work = Произведения(
            id_произведения=work_id,
            Название=title.strip(),
            Описание=description or "",
            Количество_страниц=pages or 0
        )
        db.add(new_work)

        new_book = Книги(
            id_книги=book_id,
            Название=title.strip(),
            Автор=author.strip(),
            Количество_страниц=pages or 0,
            Описание=description or "",
            Жанр=genre or "",
            ISBN=isbn or "",
            Фото_обложки=cover_url or ""
        )
        db.add(new_book)

        content = Содержание(
            id_книги=book_id,
            id_произведения=work_id,
            порядок_в_книге=1
        )
        db.add(content)

        name_parts = author.strip().split()
        if name_parts:
            author_id = str(uuid.uuid4())[:8]
            new_author = Авторы(
                id_автора=author_id,
                Имя=name_parts[0] if len(name_parts) > 0 else author,
                Фамилия=name_parts[-1] if len(name_parts) > 1 else "",
                Отчество=""
            )
            db.add(new_author)

            труд = Труд(
                id_автора=author_id,
                id_произведения=work_id,
                роль="автор"
            )
            db.add(труд)

        db.flush()
        created_book_id = book_id
        created_work_id = work_id

        if cover_file:
            cover_content = await cover_file.read()
            new_book.Фото_данные = cover_content
            new_book.Фото_тип = cover_file.content_type

        db.commit()
    else:
        created_book_id = existing_book.id_книги
        content = db.query(Содержание).filter(
            Содержание.id_книги == existing_book.id_книги
        ).first()
        created_work_id = content.id_произведения if content else None

        if cover_file and not existing_book.Фото_данные:
            cover_content = await cover_file.read()
            existing_book.Фото_данные = cover_content
            existing_book.Фото_тип = cover_file.content_type
            db.commit()

    existing_user_book = db.query(Сессия_статус).filter(
        and_(
            Сессия_статус.id_пользователя == user_id,
            Сессия_статус.id_произведения == created_work_id
        )
    ).first()

    if existing_user_book:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "BOOK_ALREADY_EXISTS",
                "message": f"Книга '{title}' уже есть в вашей библиотеке",
                "book_id": created_book_id,
                "current_status": existing_user_book.Статус
            }
        )

    new_status = Сессия_статус(
        id_пользователя=user_id,
        id_произведения=created_work_id,
        Статус="Хочу прочитать",
        current_page=0,
        added_date=datetime.now().isoformat()
    )
    db.add(new_status)
    db.commit()

    return {
        "message": f"Книга '{title}' добавлена в библиотеку (статус: Хочу прочитать)",
        "book_id": created_book_id,
        "status": "WANT_TO_READ",
        "in_wishlist": True
    }


@router.post("/user/{user_id}/add-to-library", tags=["Библиотека"])
async def add_to_library(
        user_id: str,
        title: str,
        author: str,
        description: Optional[str] = None,
        genre: Optional[str] = None,
        pages: Optional[int] = None,
        isbn: Optional[str] = None,
        cover_url: Optional[str] = None,
        cover_file: Optional[UploadFile] = None,
        db: Session = Depends(get_db)
):
    """Добавляет книгу в библиотеку со статусом 'Хочу прочитать'"""
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    existing_book = None
    if isbn:
        existing_book = db.query(Книги).filter(Книги.ISBN == isbn).first()

    if not existing_book:
        existing_book = db.query(Книги).filter(
            and_(
                Книги.Название.ilike(title.strip()),
                Книги.Автор.ilike(author.strip())
            )
        ).first()

    if not existing_book:
        book_id = str(uuid.uuid4())[:8]
        work_id = str(uuid.uuid4())[:8]

        new_work = Произведения(
            id_произведения=work_id,
            Название=title.strip(),
            Описание=description or "",
            Количество_страниц=pages or 0
        )
        db.add(new_work)

        new_book = Книги(
            id_книги=book_id,
            Название=title.strip(),
            Автор=author.strip(),
            Количество_страниц=pages or 0,
            Описание=description or "",
            Жанр=genre or "",
            ISBN=isbn or "",
            Фото_обложки=cover_url or ""
        )
        db.add(new_book)

        content = Содержание(
            id_книги=book_id,
            id_произведения=work_id,
            порядок_в_книге=1
        )
        db.add(content)

        name_parts = author.strip().split()
        if name_parts:
            author_id = str(uuid.uuid4())[:8]
            new_author = Авторы(
                id_автора=author_id,
                Имя=name_parts[0] if len(name_parts) > 0 else author,
                Фамилия=name_parts[-1] if len(name_parts) > 1 else "",
                Отчество=""
            )
            db.add(new_author)

            труд = Труд(
                id_автора=author_id,
                id_произведения=work_id,
                роль="автор"
            )
            db.add(труд)

        db.flush()
        created_book_id = book_id
        created_work_id = work_id

        if cover_file:
            cover_content = await cover_file.read()
            new_book.Фото_данные = cover_content
            new_book.Фото_тип = cover_file.content_type

        db.commit()
    else:
        created_book_id = existing_book.id_книги
        content = db.query(Содержание).filter(
            Содержание.id_книги == existing_book.id_книги
        ).first()
        created_work_id = content.id_произведения if content else None

    existing_status = db.query(Сессия_статус).filter(
        and_(
            Сессия_статус.id_пользователя == user_id,
            Сессия_статус.id_произведения == created_work_id
        )
    ).first()

    if existing_status:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "BOOK_ALREADY_IN_LIBRARY",
                "message": f"Книга '{title}' уже есть в библиотеке",
                "book_id": created_book_id,
                "current_status": existing_status.Статус
            }
        )

    new_status = Сессия_статус(
        id_пользователя=user_id,
        id_произведения=created_work_id,
        Статус="Хочу прочитать",
        current_page=0,
        added_date=datetime.now().isoformat()
    )
    db.add(new_status)
    db.commit()

    return {
        "message": f"Книга '{title}' добавлена в библиотеку (Хочу прочитать)",
        "book_id": created_book_id,
        "status": "WANT_TO_READ",
        "in_library": True
    }


# ============================================
# ВИШЛИСТ
# ============================================

@router.get("/user/{user_id}/wishlist", response_model=List[ApiBookWithProgress], tags=["Вишлист"])
def get_user_wishlist(
        user_id: str,
        db: Session = Depends(get_db)
):
    """Получить вишлист (книги со статусом 'Хочу купить')"""
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        return []

    wishlist_items = db.query(Вишлист).filter(
        Вишлист.id_пользователя == user_id
    ).all()

    result = []
    for item in wishlist_items:
        книга = db.query(Книги).filter(Книги.id_книги == item.id_книги).first()
        if not книга:
            continue

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
            userId=user_id,
            bookId=книга.id_книги,
            status=BookStatus.WANTS,
            currentPage=0,
            rating=0.0,
            review="",
            startDate="",
            endDate="",
            addedDate=item.дата_добавления or "",
            readingTimeMinutes=0
        )

        result.append(ApiBookWithProgress(
            book=kotlin_book,
            userBook=kotlin_user_book,
            progress=0.0
        ))

    return result


@router.post("/user/{user_id}/add-to-wishlist", tags=["Вишлист"])
async def add_to_wishlist(
        user_id: str,
        title: str,
        author: str,
        description: Optional[str] = None,
        pages: Optional[int] = None,
        isbn: Optional[str] = None,
        cover_url: Optional[str] = None,
        cover_file: Optional[UploadFile] = None,
        db: Session = Depends(get_db)
):
    """Добавляет книгу в вишлист со статусом 'Хочу купить'"""
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    existing_book = None
    if isbn:
        existing_book = db.query(Книги).filter(Книги.ISBN == isbn).first()

    if not existing_book:
        existing_book = db.query(Книги).filter(
            and_(
                Книги.Название.ilike(title.strip()),
                Книги.Автор.ilike(author.strip())
            )
        ).first()

    if not existing_book:
        book_id = str(uuid.uuid4())[:8]
        work_id = str(uuid.uuid4())[:8]

        new_work = Произведения(
            id_произведения=work_id,
            Название=title.strip(),
            Описание=description or "",
            Количество_страниц=pages or 0
        )
        db.add(new_work)

        new_book = Книги(
            id_книги=book_id,
            Название=title.strip(),
            Автор=author.strip(),
            Количество_страниц=pages or 0,
            Описание=description or "",
            ISBN=isbn or "",
            Фото_обложки=cover_url or ""
        )
        db.add(new_book)

        content = Содержание(
            id_книги=book_id,
            id_произведения=work_id,
            порядок_в_книге=1
        )
        db.add(content)

        name_parts = author.strip().split()
        if name_parts:
            author_id = str(uuid.uuid4())[:8]
            new_author = Авторы(
                id_автора=author_id,
                Имя=name_parts[0] if len(name_parts) > 0 else author,
                Фамилия=name_parts[-1] if len(name_parts) > 1 else "",
                Отчество=""
            )
            db.add(new_author)

            труд = Труд(
                id_автора=author_id,
                id_произведения=work_id,
                роль="автор"
            )
            db.add(труд)

        db.flush()
        created_book_id = book_id
        created_work_id = work_id

        if cover_file:
            cover_content = await cover_file.read()
            new_book.Фото_данные = cover_content
            new_book.Фото_тип = cover_file.content_type

        db.commit()
    else:
        created_book_id = existing_book.id_книги
        content = db.query(Содержание).filter(
            Содержание.id_книги == existing_book.id_книги
        ).first()
        created_work_id = content.id_произведения if content else None

    existing_wishlist = db.query(Вишлист).filter(
        and_(
            Вишлист.id_пользователя == user_id,
            Вишлист.id_книги == created_book_id
        )
    ).first()

    if existing_wishlist:
        raise HTTPException(status_code=409, detail="Книга уже в вишлисте")

    wishlist_item = Вишлист(
        id_пользователя=user_id,
        id_книги=created_book_id,
        дата_добавления=datetime.now().isoformat(),
        приоритет=1
    )
    db.add(wishlist_item)
    db.commit()

    return {
        "message": f"Книга '{title}' добавлена в вишлист",
        "book_id": created_book_id,
        "status": "WANTS",
        "in_wishlist": True
    }


@router.delete("/user/{user_id}/wishlist/{book_id}", tags=["Вишлист"])
async def remove_from_wishlist(
        user_id: str,
        book_id: str,
        db: Session = Depends(get_db)
):
    """Удаляет книгу из вишлиста"""
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    book = db.query(Книги).filter(Книги.id_книги == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    wishlist_item = db.query(Вишлист).filter(
        and_(
            Вишлист.id_пользователя == user_id,
            Вишлист.id_книги == book_id
        )
    ).first()

    if not wishlist_item:
        raise HTTPException(status_code=404, detail="Книга не найдена в вишлисте")

    db.delete(wishlist_item)
    db.commit()

    return {
        "message": f"Книга '{book.Название}' удалена из вишлиста",
        "book_id": book_id
    }


@router.put("/user/{user_id}/wishlist/{book_id}/priority", tags=["Вишлист"])
async def update_wishlist_priority(
        user_id: str,
        book_id: str,
        priority: int,
        db: Session = Depends(get_db)
):
    """Изменить приоритет книги в вишлисте (1-5)"""
    wishlist_item = db.query(Вишлист).filter(
        and_(
            Вишлист.id_пользователя == user_id,
            Вишлист.id_книги == book_id
        )
    ).first()

    if not wishlist_item:
        raise HTTPException(status_code=404, detail="Книга не найдена в вишлисте")

    if priority < 1 or priority > 5:
        raise HTTPException(status_code=400, detail="Приоритет должен быть от 1 до 5")

    wishlist_item.приоритет = priority
    db.commit()

    return {"message": f"Приоритет изменён на {priority}"}


@router.post("/user/{user_id}/move-from-wishlist-to-library/{book_id}", tags=["Вишлист"])
async def move_from_wishlist_to_library(
        user_id: str,
        book_id: str,
        db: Session = Depends(get_db)
):
    """Переносит книгу из вишлиста в библиотеку"""
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    book = db.query(Книги).filter(Книги.id_книги == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    wishlist_item = db.query(Вишлист).filter(
        and_(
            Вишлист.id_пользователя == user_id,
            Вишлист.id_книги == book_id
        )
    ).first()

    if not wishlist_item:
        raise HTTPException(status_code=404, detail="Книга не найдена в вишлисте")

    content = db.query(Содержание).filter(Содержание.id_книги == book_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="Связь книги с произведением не найдена")

    existing_status = db.query(Сессия_статус).filter(
        and_(
            Сессия_статус.id_пользователя == user_id,
            Сессия_статус.id_произведения == content.id_произведения
        )
    ).first()

    if existing_status:
        raise HTTPException(status_code=409, detail="Книга уже есть в библиотеке")

    db.delete(wishlist_item)

    new_status = Сессия_статус(
        id_пользователя=user_id,
        id_произведения=content.id_произведения,
        Статус="Хочу прочитать",
        current_page=0,
        added_date=datetime.now().isoformat()
    )
    db.add(new_status)
    db.commit()

    return {
        "message": f"Книга '{book.Название}' перенесена из вишлиста в библиотеку",
        "book_id": book_id,
        "old_status": "WANTS",
        "new_status": "WANT_TO_READ"
    }


# ============================================
# КАТАЛОГ КНИГ
# ============================================

@router.get("/books", response_model=List[KotlinBook], tags=["Каталог книг"])
def get_all_books(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    книги = db.query(Книги).offset(skip).limit(limit).all()
    result = []

    for книга in книги:
        авторы_список = []
        содержание = db.query(Содержание).filter(Содержание.id_книги == книга.id_книги).all()
        for с in содержание:
            труд = db.query(Труд).filter(Труд.id_произведения == с.id_произведения).all()
            for t in труд:
                автор = db.query(Авторы).filter(Авторы.id_автора == t.id_автора).first()
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


@router.get("/books/{book_id}", response_model=KotlinBook, tags=["Каталог книг"])
def get_book(book_id: str, db: Session = Depends(get_db)):
    """Получить конкретную книгу по ID с обложкой из БД"""
    книга = db.query(Книги).filter(Книги.id_книги == book_id).first()
    if not книга:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    авторы = []
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
                авторы.append(автор_name)

    return KotlinBook.from_db_book(книга, авторы)


@router.get("/books/search", response_model=List[KotlinBook], tags=["Каталог книг"])
def search_books(query: str, db: Session = Depends(get_db)):
    if not query or len(query) < 2:
        return []

    search_pattern = f"%{query}%"
    книги = db.query(Книги).filter(
        or_(Книги.Название.ilike(search_pattern), Книги.Автор.ilike(search_pattern))
    ).limit(20).all()

    result = []
    for книга in книги:
        авторы = []
        содержание = db.query(Содержание).filter(Содержание.id_книги == книга.id_книги).all()
        for с in содержание:
            труд = db.query(Труд).filter(Труд.id_произведения == с.id_произведения).all()
            for t in труд:
                автор = db.query(Авторы).filter(Авторы.id_автора == t.id_автора).first()
                if автор:
                    автор_name = f"{автор.Имя} {автор.Фамилия or ''}".strip()
                    if автор_name not in авторы:
                        авторы.append(автор_name)

        result.append(KotlinBook.from_db_book(книга, авторы))

    return result


@router.post("/books/create", tags=["Каталог книг"])
async def create_book(
        title: str,
        author: str,
        pages: Optional[int] = None,
        description: Optional[str] = None,
        genre: Optional[str] = None,
        isbn: Optional[str] = None,
        published_date: Optional[str] = None,
        publisher: Optional[str] = None,
        cover_file: Optional[UploadFile] = None,
        db: Session = Depends(get_db)
):
    """Создание новой книги в каталоге"""
    existing = db.query(Книги).filter(
        and_(
            Книги.Название.ilike(title.strip()),
            Книги.Автор.ilike(author.strip())
        )
    ).first()

    if existing:
        return {"message": "Книга уже существует", "book_id": existing.id_книги}

    book_id = str(uuid.uuid4())[:8]
    work_id = str(uuid.uuid4())[:8]

    new_work = Произведения(
        id_произведения=work_id,
        Название=title.strip(),
        Описание=description or "",
        Количество_страниц=pages or 0
    )
    db.add(new_work)

    new_book = Книги(
        id_книги=book_id,
        Название=title.strip(),
        Автор=author.strip(),
        Количество_страниц=pages or 0,
        Описание=description or "",
        Жанр=genre or "",
        ISBN=isbn or "",
        год_издания=published_date or "",
        издательство=publisher or ""
    )
    db.add(new_book)

    content = Содержание(
        id_книги=book_id,
        id_произведения=work_id,
        порядок_в_книге=1
    )
    db.add(content)

    author_id = str(uuid.uuid4())[:8]
    name_parts = author.strip().split()
    new_author = Авторы(
        id_автора=author_id,
        Имя=name_parts[0] if len(name_parts) > 0 else author,
        Фамилия=name_parts[-1] if len(name_parts) > 1 else "",
        Отчество=""
    )
    db.add(new_author)

    труд = Труд(
        id_автора=author_id,
        id_произведения=work_id,
        роль="автор"
    )
    db.add(труд)

    if cover_file:
        cover_content = await cover_file.read()
        new_book.Фото_данные = cover_content
        new_book.Фото_тип = cover_file.content_type

    db.commit()

    return {"message": "Книга создана", "book_id": book_id}


@router.put("/books/{book_id}", tags=["Каталог книг"])
async def update_book(
        book_id: str,
        title: Optional[str] = None,
        author: Optional[str] = None,
        pages: Optional[int] = None,
        description: Optional[str] = None,
        genre: Optional[str] = None,
        isbn: Optional[str] = None,
        published_date: Optional[str] = None,
        publisher: Optional[str] = None,
        db: Session = Depends(get_db)
):
    """Обновление информации о книге"""
    book = db.query(Книги).filter(Книги.id_книги == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    if title:
        book.Название = title
    if author:
        book.Автор = author
    if pages:
        book.Количество_страниц = pages
    if description:
        book.Описание = description
    if genre:
        book.Жанр = genre
    if isbn:
        book.ISBN = isbn
    if published_date:
        book.год_издания = published_date
    if publisher:
        book.издательство = publisher

    book.updated_at = datetime.now()
    db.commit()

    return {"message": "Книга обновлена"}


@router.delete("/books/{book_id}", tags=["Каталог книг"])
async def delete_book(
        book_id: str,
        db: Session = Depends(get_db)
):
    """Удаление книги из каталога (только если нет связей с пользователями)"""
    book = db.query(Книги).filter(Книги.id_книги == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    content = db.query(Содержание).filter(Содержание.id_книги == book_id).first()
    if content:
        status_exists = db.query(Сессия_статус).filter(
            Сессия_статус.id_произведения == content.id_произведения
        ).first()
        if status_exists:
            raise HTTPException(
                status_code=400,
                detail="Нельзя удалить книгу, которая есть в библиотеке пользователей"
            )

    db.delete(book)
    db.commit()

    return {"message": "Книга удалена"}


# @router.post("/books/{book_id}/upload-cover", tags=["Каталог книг"])
# async def upload_book_cover(
#         book_id: str,
#         file: UploadFile = File(...),
#         db: Session = Depends(get_db)
# ):
#     """Загружает обложку в БД и на Яндекс.Диск"""
#     book = db.query(Книги).filter(Книги.id_книги == book_id).first()
#     if not book:
#         raise HTTPException(status_code=404, detail="Книга не найдена")
#
#     allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
#     file_extension = os.path.splitext(file.filename)[1].lower()
#     if file_extension not in allowed_extensions:
#         raise HTTPException(
#             status_code=400,
#             detail="Можно загружать только изображения (jpg, png, gif, webp)"
#         )
#
#     try:
#         result = await upload_cover_to_yandex_disk_and_db(file, book_id, db)
#
#         return {
#             "message": "Обложка успешно загружена и сохранена в базу данных",
#             "cover_url": result.get("cover_url"),
#             "cover_data": result.get("cover_data"),
#             "cover_type": result.get("cover_type")
#         }
#
#     except Exception as e:
#         print(f"Ошибка при загрузке обложки: {e}")
#         raise HTTPException(status_code=500, detail=f"Не удалось загрузить обложку: {str(e)}")


@router.post("/books/{book_id}/upload-cover", tags=["Каталог книг"])
async def upload_book_cover(
        book_id: str,
        file: UploadFile = File(...),
        db: Session = Depends(get_db)
):
    """Загружает обложку на Google Drive"""
    book = db.query(Книги).filter(Книги.id_книги == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    file_extension = os.path.splitext(file.filename)[1].lower()
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Можно загружать только изображения (jpg, png, gif, webp)"
        )

    try:
        cover_url = await upload_cover_to_google_drive(file, book_id)

        # Сохраняем URL в БД
        book.Фото_обложки = cover_url
        db.commit()

        return {
            "message": "Обложка успешно загружена",
            "cover_url": cover_url
        }

    except Exception as e:
        print(f"Ошибка при загрузке обложки: {e}")
        raise HTTPException(status_code=500, detail=f"Не удалось загрузить обложку: {str(e)}")




@router.get("/covers/{book_id}", tags=["Каталог книг"])
def get_cover(book_id: str, db: Session = Depends(get_db)):
    """Отдаёт обложку книги как изображение"""
    book = db.query(Книги).filter(Книги.id_книги == book_id).first()
    if not book or not book.Фото_данные:
        raise HTTPException(status_code=404, detail="Обложка не найдена")

    return Response(
        content=book.Фото_данные,
        media_type=book.Фото_тип or "image/jpeg"
    )


# ============================================
# ПОИСК КНИГ (Внешние API)
# ============================================

@router.get("/search/combined", tags=["Поиск книг"])
async def combined_book_search(
        query: str,
        db: Session = Depends(get_db)
):
    """Комбинированный поиск книг из всех источников"""
    if not query or len(query) < 2:
        return {"found": 0, "books": [], "message": "Запрос слишком короткий"}

    results = await combined_search.search_all(query, db)

    return {
        "found": len(results),
        "query": query,
        "books": results,
        "sources": ["Google Books", "OpenLibrary", "Apple iTunes", "Локальная база"]
    }


@router.get("/search/combined/isbn/{isbn}", tags=["Поиск книг"])
async def combined_search_by_isbn(
        isbn: str,
        db: Session = Depends(get_db)
):
    """Поиск книги по ISBN во всех источниках"""
    local_book = db.query(Книги).filter(Книги.ISBN == isbn).first()
    if local_book:
        return {
            "found": True,
            "book": {
                "title": local_book.Название,
                "author": local_book.Автор,
                "description": local_book.Описание,
                "pages": local_book.Количество_страниц,
                "isbn": local_book.ISBN,
                "source": "Локальная база",
                "local_id": local_book.id_книги
            }
        }

    results = await combined_search.search_all(isbn)

    if results:
        return {"found": True, "book": results[0]}
    else:
        return {"found": False, "message": "Книга не найдена ни в одном источнике"}


# ============================================
# ЦИТАТЫ
# ============================================

@router.post("/user/{user_id}/quotes", tags=["Цитаты"])
async def add_quote(
        user_id: str,
        book_id: str,
        text: str,
        page: Optional[int] = None,
        tags: Optional[List[str]] = None,  # список названий тэгов
        db: Session = Depends(get_db)
):
    """Добавить цитату из книги с персональными тэгами"""
    # ... проверки книги и произведения ...

    quote_id = str(uuid.uuid4())[:8]
    new_quote = Цитаты(
        id_цитаты=quote_id,
        id_пользователя=user_id,
        id_произведения=content.id_произведения,
        Текст=text,
        Страница=page or 0,
        Дата=datetime.now().isoformat()
    )
    db.add(new_quote)
    db.flush()

    # Добавляем тэги (только для этого пользователя)
    if tags:
        for tag_name in tags:
            # Ищем тэг у этого пользователя
            tag = db.query(Тэги).filter(
                and_(
                    Тэги.Название == tag_name,
                    Тэги.id_пользователя == user_id
                )
            ).first()

            if not tag:
                # Создаём новый тэг для этого пользователя
                tag_id = str(uuid.uuid4())[:8]
                tag = Тэги(
                    id_тэга=tag_id,
                    Название=tag_name,
                    id_пользователя=user_id,
                    color=f"#{hash(tag_name) % 0xFFFFFF:06x}"  # случайный цвет
                )
                db.add(tag)
                db.flush()

            # Связываем цитату с тэгом
            quote_tag = Связь_цитаты_тэги(
                id_цитаты=quote_id,
                id_тэга=tag.id_тэга
            )
            db.add(quote_tag)

    db.commit()

    return {"message": "Цитата добавлена", "quote_id": quote_id}


@router.get("/user/{user_id}/quotes", tags=["Цитаты"])
async def get_user_quotes(
        user_id: str,
        book_id: Optional[str] = None,
        tag: Optional[str] = None,  # 👈 фильтр по тэгу
        limit: int = 50,
        db: Session = Depends(get_db)
):
    """Получить цитаты пользователя с фильтрацией по книге или тэгу"""

    # Базовый запрос
    query = db.query(Цитаты).filter(Цитаты.id_пользователя == user_id)

    # Фильтр по книге
    if book_id:
        content = db.query(Содержание).filter(Содержание.id_книги == book_id).first()
        if content:
            query = query.filter(Цитаты.id_произведения == content.id_произведения)

    # Фильтр по тэгу
    if tag:
        # Подзапрос: цитаты, у которых есть тэг с таким названием
        subquery = db.query(Связь_цитаты_тэги.id_цитаты).join(
            Тэги
        ).filter(
            and_(
                Тэги.Название == tag,
                Тэги.id_пользователя == user_id
            )
        ).subquery()
        query = query.filter(Цитаты.id_цитаты.in_(subquery))

    quotes = query.order_by(Цитаты.created_at.desc()).limit(limit).all()

    result = []
    for q in quotes:
        # Получаем книгу
        произведение = db.query(Произведения).filter(
            Произведения.id_произведения == q.id_произведения
        ).first()

        книга = None
        if произведение:
            содержание = db.query(Содержание).filter(
                Содержание.id_произведения == произведение.id_произведения
            ).first()
            if содержание:
                книга = db.query(Книги).filter(
                    Книги.id_книги == содержание.id_книги
                ).first()

        # Получаем тэги этой цитаты
        quote_tags = db.query(Тэги).join(
            Связь_цитаты_тэги
        ).filter(
            Связь_цитаты_тэги.id_цитаты == q.id_цитаты
        ).all()

        result.append({
            "id": q.id_цитаты,
            "text": q.Текст,
            "page": q.Страница,
            "date": q.Дата,
            "book_id": книга.id_книги if книга else None,
            "book_title": книга.Название if книга else None,
            "book_author": книга.Автор if книга else None,
            "tags": [{"id": t.id_тэга, "name": t.Название, "color": t.color} for t in quote_tags]
        })

    return result


@router.get("/user/{user_id}/tags", tags=["Цитаты"])
def get_user_tags(
        user_id: str,
        db: Session = Depends(get_db)
):
    """Получить все тэги пользователя"""
    tags = db.query(Тэги).filter(Тэги.id_пользователя == user_id).all()

    return [
        {
            "id": t.id_тэга,
            "name": t.Название,
            "color": t.color,
            "quotes_count": db.query(Связь_цитаты_тэги).filter(
                Связь_цитаты_тэги.id_тэга == t.id_тэга
            ).count()
        }
        for t in tags
    ]


@router.post("/user/{user_id}/quotes/{quote_id}/tags", tags=["Цитаты"])
async def add_tag_to_quote(
        user_id: str,
        quote_id: str,
        tag_name: str,
        db: Session = Depends(get_db)
):
    """Добавить тэг к существующей цитате"""

    # Проверяем, что цитата принадлежит пользователю
    quote = db.query(Цитаты).filter(
        and_(
            Цитаты.id_цитаты == quote_id,
            Цитаты.id_пользователя == user_id
        )
    ).first()

    if not quote:
        raise HTTPException(status_code=404, detail="Цитата не найдена")

    # Ищем или создаём тэг
    tag = db.query(Тэги).filter(
        and_(
            Тэги.Название == tag_name,
            Тэги.id_пользователя == user_id
        )
    ).first()

    if not tag:
        tag_id = str(uuid.uuid4())[:8]
        tag = Тэги(
            id_тэга=tag_id,
            Название=tag_name,
            id_пользователя=user_id
        )
        db.add(tag)
        db.flush()

    # Проверяем, не связана ли уже цитата с этим тэгом
    existing = db.query(Связь_цитаты_тэги).filter(
        and_(
            Связь_цитаты_тэги.id_цитаты == quote_id,
            Связь_цитаты_тэги.id_тэга == tag.id_тэга
        )
    ).first()

    if existing:
        return {"message": "Тэг уже добавлен к этой цитате"}

    # Связываем
    quote_tag = Связь_цитаты_тэги(
        id_цитаты=quote_id,
        id_тэга=tag.id_тэга
    )
    db.add(quote_tag)
    db.commit()

    return {"message": f"Тэг '{tag_name}' добавлен к цитате"}


@router.put("/user/{user_id}/quotes/{quote_id}", tags=["Цитаты"])
async def update_quote(
        user_id: str,
        quote_id: str,
        text: Optional[str] = None,
        page: Optional[int] = None,
        tags: Optional[List[str]] = None,  # 👈 можно обновить тэги
        db: Session = Depends(get_db)
):
    """
    Обновить цитату.
    - Можно изменить текст
    - Можно изменить страницу
    - Можно заменить все тэги новым списком
    """

    # Проверяем, что цитата принадлежит пользователю
    quote = db.query(Цитаты).filter(
        and_(
            Цитаты.id_цитаты == quote_id,
            Цитаты.id_пользователя == user_id
        )
    ).first()

    if not quote:
        raise HTTPException(status_code=404, detail="Цитата не найдена")

    # 1. Обновляем текст
    if text is not None:
        quote.Текст = text

    # 2. Обновляем страницу
    if page is not None:
        quote.Страница = page

    # 3. Обновляем тэги (полная замена)
    if tags is not None:
        # Удаляем старые связи
        db.query(Связь_цитаты_тэги).filter(
            Связь_цитаты_тэги.id_цитаты == quote_id
        ).delete()

        # Добавляем новые тэги
        for tag_name in tags:
            # Ищем или создаём тэг (только для этого пользователя)
            tag = db.query(Тэги).filter(
                and_(
                    Тэги.Название == tag_name,
                    Тэги.id_пользователя == user_id
                )
            ).first()

            if not tag:
                tag_id = str(uuid.uuid4())[:8]
                tag = Тэги(
                    id_тэга=tag_id,
                    Название=tag_name,
                    id_пользователя=user_id
                )
                db.add(tag)
                db.flush()

            # Связываем
            quote_tag = Связь_цитаты_тэги(
                id_цитаты=quote_id,
                id_тэга=tag.id_тэга
            )
            db.add(quote_tag)

    quote.updated_at = datetime.now()  # если есть такое поле
    db.commit()

    return {"message": "Цитата обновлена"}


@router.delete("/user/{user_id}/quotes/{quote_id}/tags/{tag_id}", tags=["Цитаты"])
async def remove_tag_from_quote(
        user_id: str,
        quote_id: str,
        tag_id: str,
        db: Session = Depends(get_db)
):
    """Удалить тэг из цитаты"""

    # Проверяем, что тэг принадлежит пользователю
    tag = db.query(Тэги).filter(
        and_(
            Тэги.id_тэга == tag_id,
            Тэги.id_пользователя == user_id
        )
    ).first()

    if not tag:
        raise HTTPException(status_code=404, detail="Тэг не найден")

    # Удаляем связь
    quote_tag = db.query(Связь_цитаты_тэги).filter(
        and_(
            Связь_цитаты_тэги.id_цитаты == quote_id,
            Связь_цитаты_тэги.id_тэга == tag_id
        )
    ).first()

    if not quote_tag:
        raise HTTPException(status_code=404, detail="Связь не найдена")

    db.delete(quote_tag)
    db.commit()

    return {"message": "Тэг удалён из цитаты"}


@router.delete("/quotes/{quote_id}", tags=["Цитаты"])
async def delete_quote(
        quote_id: str,
        db: Session = Depends(get_db)
):
    """Удалить цитату"""
    quote = db.query(Цитаты).filter(Цитаты.id_цитаты == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Цитата не найдена")

    db.delete(quote)
    db.commit()

    return {"message": "Цитата удалена"}