from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import List, Optional
from datetime import datetime
import os
import uuid
import httpx

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

from services.yandex_disk import upload_cover_to_yandex_disk_and_db

router = APIRouter(prefix="/api", tags=["api"])


# ============================================
# ПОЛЬЗОВАТЕЛИ
# ============================================

@router.get("/users/{user_id}", response_model=KotlinUser)
def get_user(
        user_id: str,
        db: Session = Depends(get_db)
):
    """Получить информацию о пользователе"""
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        return KotlinUser(id=user_id)
    return KotlinUser.from_db_user(user)


@router.post("/users/register")
async def register_user(
        nickname: str,
        email: str,
        password: str,
        db: Session = Depends(get_db)
):
    """Регистрация нового пользователя"""
    # Проверяем, не занят ли email
    existing = db.query(Аккаунты).filter(Аккаунты.Почта == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")

    # Проверяем никнейм
    existing_nick = db.query(Аккаунты).filter(Аккаунты.Никнейм == nickname).first()
    if existing_nick:
        raise HTTPException(status_code=400, detail="Никнейм уже занят")

    # Создаём пользователя
    user_id = str(uuid.uuid4())[:8]
    new_user = Аккаунты(
        id_пользователя=user_id,
        Никнейм=nickname,
        Почта=email,
        Пароль=password,  # В реальном проекте хэшируйте!
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


@router.put("/users/{user_id}/profile")
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
# КНИГИ ПОЛЬЗОВАТЕЛЯ
# ============================================

@router.get("/user/{user_id}/books", response_model=List[ApiBookWithProgress])
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

        # Авторы
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


@router.get("/user/{user_id}/wishlist", response_model=List[ApiBookWithProgress])
def get_user_wishlist(user_id: str, db: Session = Depends(get_db)):
    return get_user_books(user_id, BookStatus.WANT_TO_READ, db)


@router.get("/user/{user_id}/reading", response_model=List[ApiBookWithProgress])
def get_user_reading(user_id: str, db: Session = Depends(get_db)):
    return get_user_books(user_id, BookStatus.READING, db)


@router.get("/user/{user_id}/finished", response_model=List[ApiBookWithProgress])
def get_user_finished(user_id: str, db: Session = Depends(get_db)):
    return get_user_books(user_id, BookStatus.FINISHED, db)


@router.get("/user/{user_id}/stats")
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


@router.post("/user/{user_id}/book/{book_id}/add-to-wishlist")
def add_book_to_wishlist(user_id: str, book_id: str, db: Session = Depends(get_db)):
    """Добавить книгу в вишлист пользователя"""
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    книга = db.query(Книги).filter(Книги.id_книги == book_id).first()
    if not книга:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    содержание = db.query(Содержание).filter(Содержание.id_книги == book_id).first()
    if not содержание:
        raise HTTPException(status_code=404, detail="Произведение не найдено")

    existing = db.query(Сессия_статус).filter(
        and_(
            Сессия_статус.id_пользователя == user_id,
            Сессия_статус.id_произведения == содержание.id_произведения
        )
    ).first()

    if existing:
        if existing.Статус == "Хочу прочитать":
            return {"message": "Книга уже в вишлисте"}
        existing.Статус = "Хочу прочитать"
        existing.updated_at = datetime.now()
    else:
        new_status = Сессия_статус(
            id_пользователя=user_id,
            id_произведения=содержание.id_произведения,
            Статус="Хочу прочитать",
            current_page=0,
            added_date=datetime.now().isoformat()
        )
        db.add(new_status)

    wishlist_item = Вишлист(
        id_пользователя=user_id,
        id_книги=book_id,
        дата_добавления=datetime.now().isoformat(),
        приоритет=1
    )
    db.add(wishlist_item)
    db.commit()
    return {"message": "Книга добавлена в вишлист"}


@router.delete("/user/{user_id}/wishlist/{book_id}")
async def remove_from_wishlist(
        user_id: str,
        book_id: str,
        db: Session = Depends(get_db)
):
    """Удалить книгу из вишлиста"""
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

    return {"message": "Книга удалена из вишлиста"}


@router.put("/user/{user_id}/wishlist/{book_id}/priority")
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


@router.put("/user/{user_id}/book/{book_id}/status")
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


@router.put("/user/{user_id}/book/{book_id}/progress")
async def update_reading_progress(
        user_id: str,
        book_id: str,
        current_page: int,
        db: Session = Depends(get_db)
):
    """Обновить текущую страницу чтения"""
    # Получаем произведение
    content = db.query(Содержание).filter(Содержание.id_книги == book_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    # Находим статус
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

    # Если дошли до конца
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


@router.post("/user/{user_id}/reading-session")
async def add_reading_session(
        user_id: str,
        book_id: str,
        start_page: int,
        end_page: int,
        duration_minutes: int,
        db: Session = Depends(get_db)
):
    """Добавить сессию чтения (для статистики)"""
    session_id = str(uuid.uuid4())[:8]

    new_session = Сессии(
        id_сессии=session_id,
        id_пользователя=user_id,
        id_книги=book_id,
        Начальная_страница=start_page,
        Последняя_страница=end_page,
        pages_read=end_page - start_page,
        duration_minutes=duration_minutes,
        Дата_начала=datetime.now().isoformat()
    )
    db.add(new_session)
    db.commit()

    # Обновляем общее время чтения в статусе
    content = db.query(Содержание).filter(Содержание.id_книги == book_id).first()
    if content:
        status = db.query(Сессия_статус).filter(
            and_(
                Сессия_статус.id_пользователя == user_id,
                Сессия_статус.id_произведения == content.id_произведения
            )
        ).first()
        if status:
            status.reading_time_minutes += duration_minutes
            db.commit()

    return {"message": "Сессия чтения добавлена", "session_id": session_id}


@router.put("/user/{user_id}/book/{book_id}/review")
async def add_review(
        user_id: str,
        book_id: str,
        rating: float,
        review: Optional[str] = None,
        db: Session = Depends(get_db)
):
    """Добавить отзыв и оценку на книгу"""
    # Получаем произведение
    content = db.query(Содержание).filter(Содержание.id_книги == book_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    # Находим статус
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


# ============================================
# КНИГИ (КАТАЛОГ)
# ============================================

@router.get("/books", response_model=List[KotlinBook])
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


@router.post("/books/create")
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
    """Создание новой книги в каталоге (без привязки к пользователю)"""
    # Проверяем, нет ли уже такой книги
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

    # Создаём произведение
    new_work = Произведения(
        id_произведения=work_id,
        Название=title.strip(),
        Описание=description or "",
        Количество_страниц=pages or 0
    )
    db.add(new_work)

    # Создаём книгу
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

    # Связываем
    content = Содержание(
        id_книги=book_id,
        id_произведения=work_id,
        порядок_в_книге=1
    )
    db.add(content)

    # Создаём автора (упрощённо)
    author_id = str(uuid.uuid4())[:8]
    name_parts = author.strip().split()
    new_author = Авторы(
        id_автора=author_id,
        Имя=name_parts[0] if len(name_parts) > 0 else author,
        Фамилия=name_parts[-1] if len(name_parts) > 1 else "",
        Отчество=""
    )
    db.add(new_author)

    # Связываем автора с произведением
    труд = Труд(
        id_автора=author_id,
        id_произведения=work_id,
        роль="автор"
    )
    db.add(труд)

    # Обложка
    if cover_file:
        cover_content = await cover_file.read()
        new_book.Фото_данные = cover_content
        new_book.Фото_тип = cover_file.content_type

    db.commit()

    return {"message": "Книга создана", "book_id": book_id}


@router.put("/books/{book_id}")
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


@router.delete("/books/{book_id}")
async def delete_book(
        book_id: str,
        db: Session = Depends(get_db)
):
    """Удаление книги из каталога (только если нет связей с пользователями)"""
    book = db.query(Книги).filter(Книги.id_книги == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    # Проверяем, есть ли связи с пользователями
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


@router.get("/books/search", response_model=List[KotlinBook])
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


@router.get("/books/{book_id}", response_model=KotlinBook)
def get_book(book_id: str, db: Session = Depends(get_db)):
    """Получить конкретную книгу по ID с обложкой из БД"""
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

    # Конвертируем в Kotlin модель (включая base64 обложку)
    return KotlinBook.from_db_book(книга, авторы)


# ============================================
# ЗАГРУЗКА ОБЛОЖЕК
# ============================================

@router.post("/books/{book_id}/upload-cover")
async def upload_book_cover(
        book_id: str,
        file: UploadFile = File(...),
        db: Session = Depends(get_db)
):
    """Загружает обложку в БД и на Яндекс.Диск"""

    # Проверяем книгу
    book = db.query(Книги).filter(Книги.id_книги == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    # Проверяем формат
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    file_extension = os.path.splitext(file.filename)[1].lower()
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Можно загружать только изображения (jpg, png, gif, webp)"
        )

    try:
        # Загружаем в БД и на Яндекс.Диск
        result = await upload_cover_to_yandex_disk_and_db(file, book_id, db)

        return {
            "message": "Обложка успешно загружена и сохранена в базу данных",
            "cover_url": result.get("cover_url"),
            "cover_data": result.get("cover_data"),
            "cover_type": result.get("cover_type")
        }

    except Exception as e:
        print(f"Ошибка при загрузке обложки: {e}")
        raise HTTPException(status_code=500, detail=f"Не удалось загрузить обложку: {str(e)}")


# ============================================
# ЦИТАТЫ И ТЭГИ
# ============================================

@router.post("/user/{user_id}/quotes")
async def add_quote(
        user_id: str,
        book_id: str,
        text: str,
        page: Optional[int] = None,
        tags: Optional[List[str]] = None,
        db: Session = Depends(get_db)
):
    """Добавить цитату из книги"""
    # Проверяем книгу
    book = db.query(Книги).filter(Книги.id_книги == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    # Получаем произведение
    content = db.query(Содержание).filter(Содержание.id_книги == book_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="Произведение не найдено")

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

    # Добавляем теги
    if tags:
        for tag_name in tags:
            tag = db.query(Тэги).filter(Тэги.Название == tag_name).first()
            if not tag:
                # Создаём новый тег
                tag_id = str(uuid.uuid4())[:8]
                tag = Тэги(
                    id_тэга=tag_id,
                    Название=tag_name,
                    color="#3498db"
                )
                db.add(tag)
                db.flush()

            # Связываем цитату с тегом
            quote_tag = Связь_цитаты_тэги(
                id_цитаты=quote_id,
                id_тэга=tag.id_тэга
            )
            db.add(quote_tag)

    db.commit()

    return {"message": "Цитата добавлена", "quote_id": quote_id}


@router.get("/user/{user_id}/quotes")
async def get_user_quotes(
        user_id: str,
        book_id: Optional[str] = None,
        limit: int = 50,
        db: Session = Depends(get_db)
):
    """Получить цитаты пользователя (по книге или все)"""
    query = db.query(Цитаты).filter(Цитаты.id_пользователя == user_id)

    if book_id:
        content = db.query(Содержание).filter(Содержание.id_книги == book_id).first()
        if content:
            query = query.filter(Цитаты.id_произведения == content.id_произведения)

    quotes = query.order_by(Цитаты.created_at.desc()).limit(limit).all()

    result = []
    for q in quotes:
        result.append({
            "id": q.id_цитаты,
            "text": q.Текст,
            "page": q.Страница,
            "date": q.Дата
        })

    return result


@router.delete("/quotes/{quote_id}")
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


# ============================================
# ДОБАВЛЕНИЕ КНИГИ ПОЛЬЗОВАТЕЛЕМ (ОСНОВНОЙ МЕТОД)
# ============================================

@router.post("/user/{user_id}/add-book")
async def add_book_to_user(
        user_id: str,
        title: str,
        author: str,
        add_to_wishlist: bool = False,
        description: Optional[str] = None,
        genre: Optional[str] = None,
        pages: Optional[int] = None,
        isbn: Optional[str] = None,
        cover_file: Optional[UploadFile] = None,
        db: Session = Depends(get_db)
):
    """
    Добавляет книгу пользователю.
    - Если книги нет в БД → создаёт новую
    - Если книга уже есть в БД → просто связывает с пользователем
    - Если передан cover_file → сохраняет обложку сразу в БД
    - add_to_wishlist = True → добавляет в вишлист
    - add_to_wishlist = False → просто в библиотеку (статус Хочу прочитать)
    """
    # 1. Проверяем существование пользователя
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # 2. Ищем книгу в БД по названию и автору
    existing_book = db.query(Книги).filter(
        and_(
            Книги.Название.ilike(title.strip()),
            Книги.Автор.ilike(author.strip())
        )
    ).first()

    # 3. Если книги нет — создаём новую
    if not existing_book:
        book_id = str(uuid.uuid4())[:8]
        work_id = str(uuid.uuid4())[:8]

        # Создаём произведение
        new_work = Произведения(
            id_произведения=work_id,
            Название=title.strip(),
            Описание=description or "",
            Количество_страниц=pages or 0
        )
        db.add(new_work)

        # Создаём книгу
        new_book = Книги(
            id_книги=book_id,
            Название=title.strip(),
            Автор=author.strip(),
            Количество_страниц=pages or 0,
            Описание=description or "",
            Жанр=genre or "",
            ISBN=""
        )
        db.add(new_book)

        # Связываем книгу и произведение
        content = Содержание(
            id_книги=book_id,
            id_произведения=work_id,
            порядок_в_книге=1
        )
        db.add(content)

        # Создаём автора (упрощённо)
        author_id = str(uuid.uuid4())[:8]
        name_parts = author.strip().split()
        new_author = Авторы(
            id_автора=author_id,
            Имя=name_parts[0] if len(name_parts) > 0 else author,
            Фамилия=name_parts[-1] if len(name_parts) > 1 else "",
            Отчество=""
        )
        db.add(new_author)

        # Связываем автора с произведением
        труд = Труд(
            id_автора=author_id,
            id_произведения=work_id,
            роль="автор"
        )
        db.add(труд)

        db.flush()
        created_book_id = book_id
        created_work_id = work_id

        # Если передан файл обложки — сохраняем сразу
        if cover_file:
            cover_content = await cover_file.read()
            new_book.Фото_данные = cover_content
            new_book.Фото_тип = cover_file.content_type

        db.commit()
    else:
        # Книга уже есть в БД
        created_book_id = existing_book.id_книги

        # Получаем произведение для этой книги
        content = db.query(Содержание).filter(
            Содержание.id_книги == existing_book.id_книги
        ).first()
        if content:
            created_work_id = content.id_произведения
        else:
            raise HTTPException(status_code=500, detail="Ошибка связи книги с произведением")

        # Если передан файл обложки и у книги ещё нет обложки — сохраняем
        if cover_file and not existing_book.Фото_данные:
            cover_content = await cover_file.read()
            existing_book.Фото_данные = cover_content
            existing_book.Фото_тип = cover_file.content_type
            db.commit()

    # 4. Добавляем статус WANT_TO_READ для книги (всегда!)
    existing_status = db.query(Сессия_статус).filter(
        and_(
            Сессия_статус.id_пользователя == user_id,
            Сессия_статус.id_произведения == created_work_id
        )
    ).first()

    if not existing_status:
        new_status = Сессия_статус(
            id_пользователя=user_id,
            id_произведения=created_work_id,
            Статус="Хочу прочитать",
            current_page=0,
            added_date=datetime.now().isoformat()
        )
        db.add(new_status)
        db.commit()

    # 5. Если add_to_wishlist = True — добавляем в отдельную таблицу вишлиста
    if add_to_wishlist:
        existing_wishlist = db.query(Вишлист).filter(
            and_(
                Вишлист.id_пользователя == user_id,
                Вишлист.id_книги == created_book_id
            )
        ).first()

        if not existing_wishlist:
            wishlist_item = Вишлист(
                id_пользователя=user_id,
                id_книги=created_book_id,
                дата_добавления=datetime.now().isoformat(),
                приоритет=1
            )
            db.add(wishlist_item)
            db.commit()

    # 6. Формируем ответ
    return {
        "message": f"Книга '{title}' добавлена в {'вишлист' if add_to_wishlist else 'библиотеку'} (статус: Хочу прочитать)",
        "book_id": created_book_id,
        "status": "WANT_TO_READ",
        "in_wishlist": add_to_wishlist,
        "has_cover": cover_file is not None
    }


# ============================================
# КОМБИНИРОВАННЫЙ ПОИСК КНИГ
# ============================================

from services.book_search import combined_search


@router.get("/search/combined")
async def combined_book_search(
        query: str,
        db: Session = Depends(get_db)
):
    """
    Комбинированный поиск книг из всех источников:
    - Google Books
    - OpenLibrary
    - Apple iTunes
    - Локальная база данных
    """
    if not query or len(query) < 2:
        return {"found": 0, "books": [], "message": "Запрос слишком короткий"}

    results = await combined_search.search_all(query, db)

    return {
        "found": len(results),
        "query": query,
        "books": results,
        "sources": ["Google Books", "OpenLibrary", "Apple iTunes", "Локальная база"]
    }


@router.get("/search/combined/isbn/{isbn}")
async def combined_search_by_isbn(
        isbn: str,
        db: Session = Depends(get_db)
):
    """
    Поиск книги по ISBN во всех источниках
    """
    # Сначала ищем в локальной БД
    from models.sql_models import Книги

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

    # Ищем во внешних API
    results = await combined_search.search_all(isbn)

    if results:
        return {"found": True, "book": results[0]}
    else:
        return {"found": False, "message": "Книга не найдена ни в одном источнике"}

