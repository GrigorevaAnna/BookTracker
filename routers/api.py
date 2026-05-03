from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import List, Optional
from datetime import datetime
import os
import uuid
import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request

from services.book_search import combined_search
from services.google_drive import upload_cover_to_google_drive
from models.pydantic_models import normalize_language
from services.google_drive import download_and_upload_cover
from services.recommendation_service import recommendation_service

from database.database import get_db
from models.sql_models import (
    Книги, Авторы, Произведения, Труд, Содержание,
    Аккаунты, Сессия_статус, Вишлист, Сессии, Цитаты,
    Тэги, Связь_цитаты_тэги, Рекомендации_реакции, Кеш_рекомендаций
)
from models.pydantic_models import (
    ApiBookWithProgress, KotlinBook, KotlinUserBook, KotlinUser,
    BookStatus, status_from_db, status_to_db
)



router = APIRouter(prefix="/api", tags=["api"])


def normalize_language(lang: str) -> str:
    """Преобразует код языка в читаемый вид"""
    if not lang:
        return "Русский"

    lang_lower = lang.lower()

    language_map = {
        "ru": "Русский",
        "rus": "Русский",
        "en": "Английский",
        "eng": "Английский",
        "fr": "Французский",
        "fre": "Французский",
        "de": "Немецкий",
        "ger": "Немецкий",
        "es": "Испанский",
        "spa": "Испанский",
        "it": "Итальянский",
        "ita": "Итальянский",
        "zh": "Китайский",
        "chi": "Китайский",
        "ja": "Японский",
        "jp": "Японский",
        "ko": "Корейский",
        "kor": "Корейский"
    }

    return language_map.get(lang_lower, lang.capitalize() if lang else "Русский")





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
            publisher=книга.издательство or "",
            language=книга.Язык or "Русский"
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
        title: str = Query(...),
        author: str = Query(...),
        description: Optional[str] = Query(None),
        genre: Optional[str] = Query(None),
        pages: Optional[int] = Query(None),
        isbn: Optional[str] = Query(None),
        cover_url: Optional[str] = Query(None),
        language: Optional[str] = Query(None),
        db: Session = Depends(get_db)
):
    """Добавляет книгу пользователю со статусом 'Хочу прочитать'"""

    print("=" * 50)
    print(f"📥 add_book_to_user вызван")
    print(f"   user_id: {user_id}")
    print(f"   title: {title}")
    print(f"   author: {author}")
    print(f"   cover_url: {cover_url}")
    print("=" * 50)

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
            Фото_обложки=cover_url or "",
            Язык=language or "Русский"
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

        db.commit()
    else:
        created_book_id = existing_book.id_книги
        content = db.query(Содержание).filter(
            Содержание.id_книги == existing_book.id_книги
        ).first()
        created_work_id = content.id_произведения if content else None

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
        title: str = Query(...),
        author: str = Query(...),
        description: Optional[str] = Query(None),
        genre: Optional[str] = Query(None),
        pages: Optional[int] = Query(None),
        isbn: Optional[str] = Query(None),
        cover_url: Optional[str] = Query(None),
        language: Optional[str] = Query(None),
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

        # 👇 СОХРАНЯЕМ ОБЛОЖКУ НА GOOGLE DRIVE
        final_cover_url = cover_url
        if cover_url:
            final_cover_url = await download_and_upload_cover(book_id, cover_url)

        new_book = Книги(
            id_книги=book_id,
            Название=title.strip(),
            Автор=author.strip(),
            Количество_страниц=pages or 0,
            Описание=description or "",
            Жанр=genre or "",
            ISBN=isbn or "",
            Фото_обложки=final_cover_url,  # 👈 ссылка на Google Drive
            Язык=language or "Русский"
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


        db.commit()
    else:
        created_book_id = existing_book.id_книги
        content = db.query(Содержание).filter(
            Содержание.id_книги == existing_book.id_книги
        ).first()
        created_work_id = content.id_произведения if content else None

        # 👇 Если у книги нет обложки, но есть внешняя ссылка — сохраняем
        if cover_url and not existing_book.Фото_обложки:
            final_cover_url = await download_and_upload_cover(created_book_id, cover_url)
            existing_book.Фото_обложки = final_cover_url
            db.commit()

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
            publisher=книга.издательство or "",
            language=книга.Язык or "Русский"
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


@router.post("/user/{user_id}/move-to-wishlist/{book_id}", tags=["Вишлист"])
async def move_to_wishlist(
        user_id: str,
        book_id: str,
        db: Session = Depends(get_db)
):
    """
    Перемещает книгу в вишлист.

    Логика:
    - Если книга уже в библиотеке → меняет статус на WANTS и добавляет в вишлист
    - Если книги нет в библиотеке → просто добавляет в вишлист
    - Если уже в вишлисте → возвращает ошибку
    """
    print(f"\n{'=' * 60}")
    print(f"📥 MOVE-TO-WISHLIST: user={user_id}, book={book_id}")
    print(f"{'=' * 60}\n")

    # Проверяем пользователя
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Проверяем книгу
    book = db.query(Книги).filter(Книги.id_книги == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    # Проверяем, есть ли уже в вишлисте
    existing_wishlist = db.query(Вишлист).filter(
        and_(
            Вишлист.id_пользователя == user_id,
            Вишлист.id_книги == book_id
        )
    ).first()

    if existing_wishlist:
        raise HTTPException(status_code=409, detail="Книга уже в вишлисте")

    # Получаем произведение через Содержание
    content = db.query(Содержание).filter(
        Содержание.id_книги == book_id
    ).first()

    if not content:
        raise HTTPException(status_code=404, detail="Связь книги с произведением не найдена")

    work_id = content.id_произведения

    # Проверяем, есть ли книга в библиотеке (Сессия_статус)
    existing_status = db.query(Сессия_статус).filter(
        and_(
            Сессия_статус.id_пользователя == user_id,
            Сессия_статус.id_произведения == work_id
        )
    ).first()

    if existing_status:
        # Книга есть в библиотеке → меняем статус на WANTS
        old_status = existing_status.Статус
        existing_status.Статус = "Хочу"  # статус вишлиста
        existing_status.updated_at = datetime.now()
        print(f"   🔄 Статус изменён: {old_status} → Хочу")

    # Добавляем в вишлист
    wishlist_item = Вишлист(
        id_пользователя=user_id,
        id_книги=book_id,
        дата_добавления=datetime.now().isoformat(),
        приоритет=1
    )
    db.add(wishlist_item)
    db.commit()

    print(f"✅ Книга '{book.Название}' добавлена в вишлист")

    return {
        "message": f"Книга '{book.Название}' добавлена в вишлист",
        "book_id": book_id,
        "status": "WANTS",
        "in_wishlist": True,
        "previous_status": existing_status.Статус if existing_status else None
    }


@router.post("/user/{user_id}/add-to-wishlist", tags=["Вишлист"])
async def add_to_wishlist(
        user_id: str,
        title: str = Query(...),
        author: str = Query(...),
        description: Optional[str] = Query(None),
        pages: Optional[int] = Query(None),
        isbn: Optional[str] = Query(None),
        cover_url: Optional[str] = Query(None),
        language: Optional[str] = Query(None),
        db: Session = Depends(get_db)
):
    """Добавляет книгу в вишлист со статусом 'Хочу купить'"""

    # 👇 ЛОГИРОВАНИЕ
    print("\n" + "=" * 60)
    print(f"📥 ВИШЛИСТ: Запрос на добавление")
    print(f"   user_id: {user_id}")
    print(f"   title: {title}")
    print(f"   author: {author}")
    print(f"   cover_url: {cover_url}")
    print(f"   isbn: {isbn}")
    print("=" * 60 + "\n")

    try:
        # Проверяем пользователя
        user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
        if not user:
            print("❌ Пользователь не найден")
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        print("✅ Пользователь найден")

        # Ищем существующую книгу
        existing_book = None
        if isbn:
            print(f"🔍 Ищу по ISBN: {isbn}")
            existing_book = db.query(Книги).filter(Книги.ISBN == isbn).first()
            if existing_book:
                print(f"✅ Книга найдена по ISBN: {existing_book.id_книги}")

        if not existing_book:
            print(f"🔍 Ищу по названию и автору: {title} — {author}")
            existing_book = db.query(Книги).filter(
                and_(
                    Книги.Название.ilike(title.strip()),
                    Книги.Автор.ilike(author.strip())
                )
            ).first()
            if existing_book:
                print(f"✅ Книга найдена в БД: {existing_book.id_книги}")
            else:
                print("📝 Книга не найдена, создаю новую...")

        if not existing_book:
            book_id = str(uuid.uuid4())[:8]
            work_id = str(uuid.uuid4())[:8]

            print(f"   Новая книга: book_id={book_id}, work_id={work_id}")

            # Создаём произведение
            new_work = Произведения(
                id_произведения=work_id,
                Название=title.strip(),
                Описание=description or "",
                Количество_страниц=pages or 0
            )
            db.add(new_work)
            print("   ✅ Произведение создано")

            # Загружаем обложку (с обработкой ошибок)
            final_cover_url = cover_url or ""
            if cover_url:
                try:
                    print(f"   📸 Загружаю обложку: {cover_url[:60]}...")
                    final_cover_url = await download_and_upload_cover(book_id, cover_url)
                    print(f"   ✅ Обложка загружена: {final_cover_url[:60]}...")
                except Exception as e:
                    print(f"   ⚠️ Ошибка загрузки обложки: {e}")
                    final_cover_url = cover_url  # Оставляем исходную

            # Создаём книгу
            new_book = Книги(
                id_книги=book_id,
                Название=title.strip(),
                Автор=author.strip(),
                Количество_страниц=pages or 0,
                Описание=description or "",
                ISBN=isbn or "",
                Фото_обложки=final_cover_url,
                Язык=language or "Русский"
            )
            db.add(new_book)
            print("   ✅ Книга создана")

            # Связь содержание
            content = Содержание(
                id_книги=book_id,
                id_произведения=work_id,
                порядок_в_книге=1
            )
            db.add(content)
            print("   ✅ Связь Содержание создана")

            # Создаём автора
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
                print(f"   ✅ Автор создан: {author_id}")

                труд = Труд(
                    id_автора=author_id,
                    id_произведения=work_id,
                    роль="автор"
                )
                db.add(труд)
                print("   ✅ Связь Труд создана")

            db.flush()
            created_book_id = book_id
            created_work_id = work_id
            db.commit()
            print(f"   ✅ Всё сохранено в БД")

        else:
            created_book_id = existing_book.id_книги
            content = db.query(Содержание).filter(
                Содержание.id_книги == existing_book.id_книги
            ).first()
            created_work_id = content.id_произведения if content else None
            print(f"   Использую существующую книгу: {created_book_id}")

            # Обновляем обложку если нужно
            if cover_url and not existing_book.Фото_обложки:
                try:
                    print(f"   📸 Обновляю обложку: {cover_url[:60]}...")
                    final_cover_url = await download_and_upload_cover(created_book_id, cover_url)
                    existing_book.Фото_обложки = final_cover_url
                    db.commit()
                    print(f"   ✅ Обложка обновлена")
                except Exception as e:
                    print(f"   ⚠️ Ошибка обновления обложки: {e}")

        # Проверяем, нет ли уже в вишлисте
        print(f"🔍 Проверяю вишлист: user={user_id}, book={created_book_id}")
        existing_wishlist = db.query(Вишлист).filter(
            and_(
                Вишлист.id_пользователя == user_id,
                Вишлист.id_книги == created_book_id
            )
        ).first()

        if existing_wishlist:
            print("❌ Книга уже в вишлисте")
            raise HTTPException(status_code=409, detail="Книга уже в вишлисте")

        # Добавляем в вишлист
        wishlist_item = Вишлист(
            id_пользователя=user_id,
            id_книги=created_book_id,
            дата_добавления=datetime.now().isoformat(),
            приоритет=1
        )
        db.add(wishlist_item)
        db.commit()
        print(f"✅ Книга '{title}' добавлена в вишлист!")
        print("=" * 60 + "\n")

        return {
            "message": f"Книга '{title}' добавлена в вишлист",
            "book_id": created_book_id,
            "status": "WANTS",
            "in_wishlist": True
        }

    except HTTPException:
        raise  # Пробрасываем HTTPException дальше
    except Exception as e:
        print(f"\n❌ ОШИБКА в add_to_wishlist: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 60 + "\n")
        raise HTTPException(status_code=500, detail=f"Ошибка при добавлении в вишлист: {str(e)}")


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
            publisher=книга.издательство or "",
            language=книга.Язык or "Русский"
        )
        result.append(kotlin_book)

    return result


@router.get("/books/{book_id}", response_model=KotlinBook, tags=["Каталог книг"])
def get_book(book_id: str, db: Session = Depends(get_db)):
    """Получить конкретную книгу по ID"""
    книга = db.query(Книги).filter(Книги.id_книги == book_id).first()
    if not книга:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    # Получаем авторов
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

    # Создаём объект с языком
    return KotlinBook(
        id=книга.id_книги,
        title=книга.Название,
        author=", ".join(авторы) if авторы else книга.Автор,
        coverUrl=книга.Фото_обложки or "",
        description=книга.Описание or "",
        pages=книга.Количество_страниц,
        genre=книга.Жанр or "",
        isbn=книга.ISBN or "",
        publishedDate=книга.год_издания or "",
        publisher=книга.издательство or "",
        language=книга.Язык or "Русский"  # 👈 ДОБАВЬТЕ ЭТО ПОЛЕ
    )

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
        language: Optional[str] = None,
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
        издательство=publisher or "",
        Язык=language or "Русский"
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


@router.get("/search/unified", tags=["Поиск книг"])
async def unified_book_search(
        query: str,
        db: Session = Depends(get_db)
):
    """
    Единый поиск книг:
    1. Сначала ищет в локальной БД
    2. Потом во внешних API
    3. Объединяет результаты в один массив
    4. Возвращает в формате, совместимом с Kotlin Book
    """
    if not query or len(query) < 2:
        return []  # 👈 возвращаем пустой массив, если запрос короткий

    from datetime import datetime
    import uuid

    result_books = []  # 👈 ОДИН МАССИВ ДЛЯ ВСЕХ РЕЗУЛЬТАТОВ

    # ============================================
    # 1. ПОИСК В ЛОКАЛЬНОЙ БАЗЕ ДАННЫХ
    # ============================================
    search_pattern = f"%{query}%"
    db_books = db.query(Книги).filter(
        or_(
            Книги.Название.ilike(search_pattern),
            Книги.Автор.ilike(search_pattern)
        )
    ).limit(20).all()

    # Множество для отслеживания дубликатов по ISBN
    seen_isbns = set()

    for book in db_books:
        if book.ISBN:
            seen_isbns.add(book.ISBN)

        # Получаем авторов
        авторы_список = []
        содержание = db.query(Содержание).filter(
            Содержание.id_книги == book.id_книги
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

        # Формируем объект в формате Kotlin Book
        result_books.append({
            "id": book.id_книги,
            "title": book.Название,
            "author": ", ".join(авторы_список) if авторы_список else book.Автор,
            "coverUrl": book.Фото_обложки or "",
            "description": book.Описание or "",
            "pages": book.Количество_страниц,
            "genre": book.Жанр or "",
            "isbn": book.ISBN or "",
            "publishedDate": book.год_издания or "",
            "publisher": book.издательство or "",
            "language": normalize_language(book.Язык or "Русский"),
            "source": "local"
        })

    # ============================================
    # 2. ПОИСК ВО ВНЕШНИХ API
    # ============================================
    external_results = await combined_search.search_all(query, db)

    for result in external_results:
        # Пропускаем дубликаты
        if result.get("isbn") and result.get("isbn") in seen_isbns:
            continue

        # Формируем объект в формате Kotlin Book
        result_books.append({
            "id": str(uuid.uuid4())[:8],
            "title": result.get("title", ""),
            "author": result.get("author", ""),
            "coverUrl": result.get("cover_url", ""),
            "description": result.get("description", ""),
            "pages": result.get("pages", 0),
            "genre": "",
            "isbn": result.get("isbn", ""),
            "publishedDate": result.get("published_date", ""),
            "publisher": result.get("publisher", ""),
            "language": normalize_language(result.get("language", "Русский")),
            "source": result.get("source", "external")
        })

    # ============================================
    # 3. ВОЗВРАЩАЕМ ПРОСТОЙ МАССИВ
    # ============================================
    return result_books


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
        book_id: str = Query(...),
        text: str = Query(...),
        page: Optional[int] = Query(None),
        db: Session = Depends(get_db),
        request: Request = None
):
    # Получаем тэги из тела запроса
    body = await request.json()
    tags = body.get("hashTags", []) if body else None
    """Добавить цитату из книги с персональными тэгами"""

    # 1. Проверяем, существует ли книга
    book = db.query(Книги).filter(Книги.id_книги == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    # 2. Получаем произведение через связь Содержание
    content = db.query(Содержание).filter(
        Содержание.id_книги == book_id
    ).first()

    if not content:
        raise HTTPException(status_code=404, detail="Произведение не найдено")

    # 3. Создаём цитату
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

    # 4. Добавляем тэги (только для этого пользователя)
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
                    color=f"#{hash(tag_name) % 0xFFFFFF:06x}"
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


from fastapi import Request


@router.put("/user/{user_id}/quotes/{quote_id}", tags=["Цитаты"])
async def update_quote(
        user_id: str,
        quote_id: str,
        request: Request,
        db: Session = Depends(get_db)
):
    """
    Обновить цитату.
    - Можно изменить текст
    - Можно изменить страницу
    - Можно заменить все тэги новым списком
    """
    # Читаем тело запроса
    try:
        body = await request.json()
    except:
        body = {}

    text = body.get("text")
    page = body.get("page")
    tags = body.get("hashTags") or body.get("tags")  # фронт может отправлять hashTags

    print(f"📝 Обновление цитаты {quote_id}: text={text}, page={page}, tags={tags}")

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

    quote.updated_at = datetime.now()
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
    """Удалить цитату и все её связи с тэгами"""

    # 1. Находим цитату
    quote = db.query(Цитаты).filter(Цитаты.id_цитаты == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Цитата не найдена")

    # 2. Сначала удаляем все связи цитаты с тэгами
    db.query(Связь_цитаты_тэги).filter(
        Связь_цитаты_тэги.id_цитаты == quote_id
    ).delete()

    # 3. Затем удаляем саму цитату
    db.delete(quote)

    db.commit()

    return {"message": "Цитата удалена"}


# ============================================
# СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ (РАСШИРЕННАЯ)
# ============================================

@router.get("/user/{user_id}/stats/books-count", tags=["Статистика"])
def get_books_count(
        user_id: str,
        db: Session = Depends(get_db)
):
    """
    Метод 1: Сколько книг прочитал пользователь
    """
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Считаем книги со статусом "Прочитано"
    finished_count = db.query(Сессия_статус).filter(
        and_(
            Сессия_статус.id_пользователя == user_id,
            Сессия_статус.Статус == "Прочитано"
        )
    ).count()

    return {
        "user_id": user_id,
        "finished_books_count": finished_count
    }


@router.get("/user/{user_id}/stats/pages-total", tags=["Статистика"])
def get_total_pages_read(
        user_id: str,
        db: Session = Depends(get_db)
):
    """
    Метод 2: Сколько всего страниц прочитал пользователь за всё время
    """
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Суммируем все прочитанные страницы из сессий
    result = db.query(func.sum(Сессии.pages_read)).filter(
        Сессии.id_пользователя == user_id
    ).scalar()

    total_pages = result or 0

    return {
        "user_id": user_id,
        "total_pages_read": total_pages
    }


@router.get("/user/{user_id}/stats/time-total", tags=["Статистика"])
def get_total_reading_time(
        user_id: str,
        db: Session = Depends(get_db)
):
    """
    Метод 3: Сколько всего часов/минут пользователь читал всё время
    """
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Суммируем все минуты из сессий
    result = db.query(func.sum(Сессии.duration_minutes)).filter(
        Сессии.id_пользователя == user_id
    ).scalar()

    total_minutes = result or 0
    total_hours = total_minutes // 60
    remaining_minutes = total_minutes % 60

    return {
        "user_id": user_id,
        "total_minutes": total_minutes,
        "total_hours": total_hours,
        "total_hours_decimal": round(total_minutes / 60, 1),
        "formatted": f"{total_hours} ч {remaining_minutes} мин"
    }


@router.get("/user/{user_id}/stats/daily-average", tags=["Статистика"])
def get_daily_average(
        user_id: str,
        db: Session = Depends(get_db)
):
    """
    Метод 4: Сколько минут/день пользователь читает (в среднем)
    """
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Получаем все сессии с датами
    sessions = db.query(Сессии.Дата_начала, Сессии.duration_minutes).filter(
        Сессии.id_пользователя == user_id
    ).all()

    if not sessions:
        return {
            "user_id": user_id,
            "average_minutes_per_day": 0,
            "average_hours_per_day": 0,
            "days_with_reading": 0,
            "message": "Нет данных о чтении"
        }

    # Группируем по дням (уникальные даты)
    daily_totals = {}
    for session in sessions:
        if session.Дата_начала:
            # Обработка даты: если это объект date, преобразуем в строку
            if hasattr(session.Дата_начала, 'isoformat'):
                date_str = session.Дата_начала.isoformat()
            else:
                # Если строка
                date_str = str(session.Дата_начала).split('T')[0] if 'T' in str(session.Дата_начала) else str(
                    session.Дата_начала)

            daily_totals[date_str] = daily_totals.get(date_str, 0) + (session.duration_minutes or 0)

    if not daily_totals:
        return {
            "user_id": user_id,
            "average_minutes_per_day": 0,
            "average_hours_per_day": 0,
            "days_with_reading": 0
        }

    # Считаем среднее
    total_minutes = sum(daily_totals.values())
    days_count = len(daily_totals)
    avg_minutes = total_minutes // days_count
    avg_hours = round(avg_minutes / 60, 1)

    return {
        "user_id": user_id,
        "average_minutes_per_day": avg_minutes,
        "average_hours_per_day": avg_hours,
        "days_with_reading": days_count,
        "total_minutes": total_minutes
    }


@router.get("/user/{user_id}/stats/streak", tags=["Статистика"])
def get_reading_streak(
        user_id: str,
        db: Session = Depends(get_db)
):
    """
    Метод 5: Сколько дней пользователь читает подряд (текущая серия) и рекорд
    """
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Получаем все уникальные даты сессий
    sessions = db.query(Сессии.Дата_начала).filter(
        Сессии.id_пользователя == user_id
    ).all()

    if not sessions:
        return {
            "user_id": user_id,
            "current_streak": 0,
            "record_streak": 0,
            "message": "Нет данных о чтении"
        }

    # Извлекаем уникальные даты
    dates = set()
    for session in sessions:
        if session.Дата_начала:
            # Обработка даты
            if hasattr(session.Дата_начала, 'isoformat'):
                date_str = session.Дата_начала.isoformat()
            else:
                date_str = str(session.Дата_начала).split('T')[0] if 'T' in str(session.Дата_начала) else str(
                    session.Дата_начала)
            dates.add(date_str)

    # Сортируем даты
    sorted_dates = sorted(dates)

    # Преобразуем в объекты date
    from datetime import datetime, timedelta
    date_objects = []
    for d in sorted_dates:
        try:
            if isinstance(d, str):
                date_objects.append(datetime.strptime(d, '%Y-%m-%d').date())
            else:
                date_objects.append(d)
        except:
            pass

    if not date_objects:
        return {
            "user_id": user_id,
            "current_streak": 0,
            "record_streak": 0
        }

    # Вычисляем текущую серию (начиная с сегодняшнего дня)
    today = datetime.now().date()
    current_streak = 0
    check_date = today

    while check_date in date_objects:
        current_streak += 1
        check_date -= timedelta(days=1)

    # Вычисляем рекордную серию
    max_streak = 0
    current = 1

    for i in range(1, len(date_objects)):
        diff = (date_objects[i] - date_objects[i - 1]).days
        if diff == 1:
            current += 1
        else:
            max_streak = max(max_streak, current)
            current = 1
    max_streak = max(max_streak, current)

    return {
        "user_id": user_id,
        "current_streak": current_streak,
        "record_streak": max_streak,
        "last_reading_date": str(date_objects[-1]) if date_objects else None
    }



@router.get("/user/{user_id}/stats/all", tags=["Статистика"])
def get_all_stats(user_id: str, db: Session = Depends(get_db)):
    """
    Получить ВСЮ статистику одним запросом
    """
    from datetime import datetime, timedelta

    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # 1. Количество прочитанных книг
    finished_count = db.query(Сессия_статус).filter(
        and_(
            Сессия_статус.id_пользователя == user_id,
            Сессия_статус.Статус == "Прочитано"
        )
    ).count()

    # 2. Всего страниц
    total_pages = db.query(func.sum(Сессии.pages_read)).filter(
        Сессии.id_пользователя == user_id
    ).scalar() or 0

    # 3. Всего времени
    total_minutes = db.query(func.sum(Сессии.duration_minutes)).filter(
        Сессии.id_пользователя == user_id
    ).scalar() or 0

    # 4. Среднее в день
    sessions = db.query(Сессии.Дата_начала, Сессии.duration_minutes).filter(
        Сессии.id_пользователя == user_id
    ).all()

    daily_totals = {}
    for session in sessions:
        # Обработка разных типов даты
        if session.Дата_начала:
            # Если это объект date, преобразуем в строку
            if hasattr(session.Дата_начала, 'isoformat'):
                date_str = session.Дата_начала.isoformat()
            else:
                # Если строка
                date_str = str(session.Дата_начала).split('T')[0] if 'T' in str(session.Дата_начала) else str(
                    session.Дата_начала)

            daily_totals[date_str] = daily_totals.get(date_str, 0) + (session.duration_minutes or 0)

    if daily_totals:
        avg_minutes = sum(daily_totals.values()) // len(daily_totals)
        avg_hours = round(avg_minutes / 60, 1)
    else:
        avg_minutes = 0
        avg_hours = 0

    # 5. Серии (streak)
    dates = set()
    for session in sessions:
        if session.Дата_начала:
            if hasattr(session.Дата_начала, 'isoformat'):
                date_str = session.Дата_начала.isoformat()
            else:
                date_str = str(session.Дата_начала).split('T')[0] if 'T' in str(session.Дата_начала) else str(
                    session.Дата_начала)
            dates.add(date_str)

    sorted_dates = sorted(dates)
    date_objects = []
    for d in sorted_dates:
        try:
            # Пробуем распарсить строку
            if isinstance(d, str):
                date_objects.append(datetime.strptime(d, '%Y-%m-%d').date())
            else:
                date_objects.append(d)
        except:
            pass

    # Текущая серия
    today = datetime.now().date()
    current_streak = 0
    check_date = today
    while check_date in date_objects:
        current_streak += 1
        check_date -= timedelta(days=1)

    # Рекордная серия
    max_streak = 0
    current = 1
    for i in range(1, len(date_objects)):
        diff = (date_objects[i] - date_objects[i - 1]).days
        if diff == 1:
            current += 1
        else:
            max_streak = max(max_streak, current)
            current = 1
    max_streak = max(max_streak, current)

    return {
        "totalBooks": finished_count,           # было finished_books
        "totalPages": total_pages,              # было total_pages_read
        "totalReadingMinutes": total_minutes,   # было total_minutes_read
        "currentStreak": current_streak,        # было current_streak
        "longestStreak": max_streak,            # было record_streak
        "avgDailyMinutes": avg_minutes,         # было average_minutes_per_day
        "activityData": {}  # если нужно, добавьте данные по дням
    }


@router.get("/user/{user_id}/stats/pages-per-day", tags=["Статистика"])
def get_pages_per_day(
        user_id: str,
        days: int = 30,
        db: Session = Depends(get_db)
):
    """
    Метод: сколько страниц в день пользователь прочитал за последние N дней
    """
    from datetime import datetime, timedelta

    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)

    # Преобразуем даты в строки для сравнения
    start_date_str = start_date.isoformat()

    # Получаем сессии пользователя
    sessions = db.query(Сессии).filter(
        and_(
            Сессии.id_пользователя == user_id,
            Сессии.Дата_начала >= start_date_str
        )
    ).all()

    # Группируем страницы по дням
    daily_pages = {}
    for session in sessions:
        if session.Дата_начала:
            # Обработка даты
            if hasattr(session.Дата_начала, 'isoformat'):
                date_str = session.Дата_начала.isoformat()
            else:
                date_str = str(session.Дата_начала).split('T')[0] if 'T' in str(session.Дата_начала) else str(
                    session.Дата_начала)
            daily_pages[date_str] = daily_pages.get(date_str, 0) + (session.pages_read or 0)

    # Формируем массив для последних days дней
    result = []
    for i in range(days):
        current_date = (end_date - timedelta(days=days - 1 - i)).isoformat()
        pages = daily_pages.get(current_date, 0)

        result.append({
            "date": current_date,
            "pages": pages
        })

    total_pages = sum(daily_pages.values())
    days_with_reading = len([p for p in daily_pages.values() if p > 0])
    avg_pages = round(total_pages / days, 1) if days > 0 else 0
    max_pages = max(daily_pages.values()) if daily_pages else 0

    return {
        "user_id": user_id,
        "period_days": days,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily_pages": result,
        "total_pages": total_pages,
        "days_with_reading": days_with_reading,
        "average_pages_per_day": avg_pages,
        "max_pages_in_one_day": max_pages
    }


# ============================================
# РЕКОМЕНДАЦИИ (OpenAI + кеширование + предзагрузка)
# ============================================

@router.get("/user/{user_id}/recommendations", tags=["Рекомендации"])
async def get_recommendations(
        user_id: str,
        count: int = Query(5, ge=1, le=10),
        batch: int = Query(1, ge=1),
        db: Session = Depends(get_db)
):
    """
    Получить персонализированные рекомендации книг с предзагрузкой.

    Параметры:
    - count: количество книг в одной партии (по умолчанию 5)
    - batch: номер партии (1, 2, 3...)

    Логика:
    - batch=1: генерирует первую партию и в фоне готовит batch=2
    - batch=2+: отдаёт из кеша (если готово) или генерирует

    Алгоритм:
    1. Собирает книги с высокой оценкой (4-5) из библиотеки
    2. Собирает понравившиеся книги из предыдущих рекомендаций
    3. Собирает не понравившиеся книги (учитывает, но избегает похожих)
    4. Собирает все книги из библиотеки (не показывать, но жанры учитывать)
    5. Отправляет в OpenAI для генерации рекомендаций
    6. Кеширует результат на 24 часа
    7. Обогащает обложками из разных источников
    """
    from services.recommendation_service import recommendation_service

    # Проверяем существование пользователя
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # ================================================================
    # 1. Собираем книги с высокой оценкой (4-5) из библиотеки
    # ================================================================
    highly_rated = db.query(Сессия_статус, Произведения).join(
        Произведения,
        Сессия_статус.id_произведения == Произведения.id_произведения
    ).filter(
        and_(
            Сессия_статус.id_пользователя == user_id,
            Сессия_статус.Рейтинг >= 4.0
        )
    ).all()

    highly_rated_books = []
    for status, work in highly_rated:
        content = db.query(Содержание).filter(
            Содержание.id_произведения == work.id_произведения
        ).first()
        if content:
            book = db.query(Книги).filter(Книги.id_книги == content.id_книги).first()
            if book:
                highly_rated_books.append({
                    "title": book.Название,
                    "author": book.Автор,
                    "rating": status.Рейтинг,
                    "genre": book.Жанр
                })

    # ================================================================
    # 2. Собираем понравившиеся книги из предыдущих рекомендаций
    # ================================================================
    liked_reactions = db.query(Рекомендации_реакции).filter(
        and_(
            Рекомендации_реакции.id_пользователя == user_id,
            Рекомендации_реакции.reaction == "liked"
        )
    ).all()

    liked_books = []
    for reaction in liked_reactions:
        liked_books.append({
            "title": reaction.title,
            "author": reaction.author,
            "genre": reaction.genre
        })

    # ================================================================
    # 3. Собираем не понравившиеся книги из рекомендаций (ТОЛЬКО дизлайки)
    # ================================================================
    disliked_reactions = db.query(Рекомендации_реакции).filter(
        and_(
            Рекомендации_реакции.id_пользователя == user_id,
            Рекомендации_реакции.reaction == "disliked"
        )
    ).all()

    disliked_books = []
    for reaction in disliked_reactions:
        disliked_books.append({
            "title": reaction.title,
            "author": reaction.author,
            "genre": reaction.genre
        })

    # ================================================================
    # 4. Собираем ВСЕ книги из библиотеки (просто чтобы не показывать их)
    #    НЕ добавляем в disliked! Они просто в библиотеке.
    # ================================================================
    all_user_books = set()
    user_statuses = db.query(Сессия_статус).filter(
        Сессия_статус.id_пользователя == user_id
    ).all()

    for status in user_statuses:
        work = db.query(Произведения).filter(
            Произведения.id_произведения == status.id_произведения
        ).first()
        if work:
            content = db.query(Содержание).filter(
                Содержание.id_произведения == work.id_произведения
            ).first()
            if content:
                book = db.query(Книги).filter(Книги.id_книги == content.id_книги).first()
                if book:
                    book_key = f"{book.Название} — {book.Автор}"
                    if book_key not in all_user_books:
                        all_user_books.add(book_key)
                        # Добавляем в disliked ТОЛЬКО для того чтобы исключить из показа
                        # Но нейросеть понимает что это НЕ дизлайк, а просто "уже есть"
                        disliked_books.append({
                            "title": book.Название,
                            "author": book.Автор
                        })

    # ================================================================
    # 5. Логируем статистику
    # ================================================================
    print(f"\n{'=' * 60}")
    print(f"📊 ЗАПРОС РЕКОМЕНДАЦИЙ")
    print(f"👤 Пользователь: {user_id}")
    print(f"📦 Партия: {batch}")
    print(f"⭐ Высоко оценено: {len(highly_rated_books)}")
    print(f"👍 Лайков рекомендаций: {len(liked_books)}")
    print(f"👎 Дизлайков: {len(disliked_reactions)}")
    print(f"📚 Книг в библиотеке: {len(all_user_books)}")
    print(f"🔢 Запрошено книг: {count}")
    print(f"{'=' * 60}\n")

    # ================================================================
    # 6. Получаем рекомендации (из кеша или генерируем)
    # ================================================================
    result = await recommendation_service.get_or_generate_recommendations(
        db=db,
        user_id=user_id,
        liked_books=liked_books,
        disliked_books=disliked_books,
        highly_rated_books=highly_rated_books,
        count=count,
        batch=batch
    )

    # ================================================================
    # 7. Для каждой книги проверяем предыдущие реакции
    # ================================================================
    for book in result.get("recommendations", {}).get("books", []):
        existing_reaction = db.query(Рекомендации_реакции).filter(
            and_(
                Рекомендации_реакции.id_пользователя == user_id,
                Рекомендации_реакции.title == book["title"],
                Рекомендации_реакции.author == book["author"]
            )
        ).first()
        book["previous_reaction"] = existing_reaction.reaction if existing_reaction else None

    # ================================================================
    # 8. Возвращаем результат
    # ================================================================
    return {
        **result,  # recommendations + has_more + next_batch
        "user_profile": {
            "highly_rated_count": len(highly_rated_books),
            "liked_count": len(liked_books),
            "disliked_count": len(disliked_reactions),
            "total_books_in_library": len(all_user_books)
        },
        "current_batch": batch,
        "books_in_current_batch": len(result.get("recommendations", {}).get("books", []))
    }


@router.post("/user/{user_id}/recommendations/reaction", tags=["Рекомендации"])
async def save_recommendation_reaction(
        user_id: str,
        title: str = Query(...),
        author: str = Query(...),
        reaction: str = Query(..., regex="^(liked|disliked)$"),
        genre: Optional[str] = Query(None),
        summary: Optional[str] = Query(None),
        reason: Optional[str] = Query(None),
        db: Session = Depends(get_db)
):
    """
    Сохранить реакцию пользователя на рекомендованную книгу

    reaction:
    - liked (нравится) — будет учтено в следующих рекомендациях
    - disliked (не нравится) — похожие книги будут исключены
    """
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Проверяем, не было ли уже реакции
    existing = db.query(Рекомендации_реакции).filter(
        and_(
            Рекомендации_реакции.id_пользователя == user_id,
            Рекомендации_реакции.title == title,
            Рекомендации_реакции.author == author
        )
    ).first()

    if existing:
        # Обновляем существующую реакцию
        existing.reaction = reaction
        if genre:
            existing.genre = genre
        if summary:
            existing.summary = summary
        if reason:
            existing.reason = reason
        message = f"Реакция обновлена на '{reaction}'"
    else:
        # Создаём новую реакцию
        new_reaction = Рекомендации_реакции(
            id_пользователя=user_id,
            title=title,
            author=author,
            reaction=reaction,
            genre=genre,
            summary=summary,
            reason=reason
        )
        db.add(new_reaction)
        message = f"Реакция '{reaction}' сохранена"

    db.commit()

    # Очищаем кеш рекомендаций при новой реакции
    # (чтобы следующие рекомендации учли изменения)
    db.query(Кеш_рекомендаций).filter(
        Кеш_рекомендаций.id_пользователя == user_id
    ).delete()
    db.commit()

    return {
        "message": message,
        "reaction": reaction,
        "title": title,
        "author": author,
        "cache_cleared": True
    }


@router.get("/user/{user_id}/recommendations/history", tags=["Рекомендации"])
async def get_recommendation_history(
        user_id: str,
        reaction: Optional[str] = Query(None, regex="^(liked|disliked)$"),
        limit: int = Query(50, ge=1, le=100),
        db: Session = Depends(get_db)
):
    """
    Получить историю реакций на рекомендации

    Фильтр по reaction:
    - liked (только понравившиеся)
    - disliked (только не понравившиеся)
    - без фильтра (все)
    """
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    query = db.query(Рекомендации_реакции).filter(
        Рекомендации_реакции.id_пользователя == user_id
    )

    if reaction:
        query = query.filter(Рекомендации_реакции.reaction == reaction)

    reactions = query.order_by(
        Рекомендации_реакции.created_at.desc()
    ).limit(limit).all()

    return {
        "total": len(reactions),
        "reactions": [
            {
                "title": r.title,
                "author": r.author,
                "reaction": r.reaction,
                "genre": r.genre,
                "summary": r.summary,
                "reason": r.reason,
                "date": r.created_at.isoformat() if r.created_at else None
            }
            for r in reactions
        ]
    }


@router.get("/user/{user_id}/recommendations/stats", tags=["Рекомендации"])
async def get_recommendation_stats(
        user_id: str,
        db: Session = Depends(get_db)
):
    """
    Получить статистику по рекомендациям
    """
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Общая статистика
    total = db.query(Рекомендации_реакции).filter(
        Рекомендации_реакции.id_пользователя == user_id
    ).count()

    liked_count = db.query(Рекомендации_реакции).filter(
        and_(
            Рекомендации_реакции.id_пользователя == user_id,
            Рекомендации_реакции.reaction == "liked"
        )
    ).count()

    disliked_count = db.query(Рекомендации_реакции).filter(
        and_(
            Рекомендации_реакции.id_пользователя == user_id,
            Рекомендации_реакции.reaction == "disliked"
        )
    ).count()

    # Кешированные партии
    cached_batches = db.query(Кеш_рекомендаций).filter(
        and_(
            Кеш_рекомендаций.id_пользователя == user_id,
            Кеш_рекомендаций.expires_at > datetime.now()
        )
    ).count()

    # Популярные жанры среди понравившихся
    liked_genres = db.query(
        Рекомендации_реакции.genre,
        func.count().label('count')
    ).filter(
        and_(
            Рекомендации_реакции.id_пользователя == user_id,
            Рекомендации_реакции.reaction == "liked",
            Рекомендации_реакции.genre.isnot(None),
            Рекомендации_реакции.genre != ""
        )
    ).group_by(Рекомендации_реакции.genre).order_by(
        func.count().desc()
    ).all()

    return {
        "total_reactions": total,
        "liked": liked_count,
        "disliked": disliked_count,
        "like_rate": round(liked_count / total * 100, 1) if total > 0 else 0,
        "cached_batches_available": cached_batches,
        "favorite_genres": [
            {"genre": genre, "count": count}
            for genre, count in liked_genres
        ]
    }


@router.delete("/user/{user_id}/recommendations/reaction", tags=["Рекомендации"])
async def delete_recommendation_reaction(
        user_id: str,
        title: str = Query(...),
        author: str = Query(...),
        db: Session = Depends(get_db)
):
    """Удалить реакцию на книгу и очистить кеш"""
    reaction = db.query(Рекомендации_реакции).filter(
        and_(
            Рекомендации_реакции.id_пользователя == user_id,
            Рекомендации_реакции.title == title,
            Рекомендации_реакции.author == author
        )
    ).first()

    if not reaction:
        raise HTTPException(status_code=404, detail="Реакция не найдена")

    db.delete(reaction)

    # Очищаем кеш
    db.query(Кеш_рекомендаций).filter(
        Кеш_рекомендаций.id_пользователя == user_id
    ).delete()

    db.commit()

    return {
        "message": f"Реакция на '{title}' удалена",
        "cache_cleared": True
    }


@router.delete("/user/{user_id}/recommendations/cache", tags=["Рекомендации"])
async def clear_recommendations_cache(
        user_id: str,
        db: Session = Depends(get_db)
):
    """Очистить кеш рекомендаций (для принудительного обновления)"""
    deleted = db.query(Кеш_рекомендаций).filter(
        Кеш_рекомендаций.id_пользователя == user_id
    ).delete()
    db.commit()

    return {
        "message": f"Кеш очищен",
        "deleted_entries": deleted
    }