from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Optional
from datetime import datetime
import os

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
        if db_status == "Хочу прочитать": stats["wishlist"] = count
        elif db_status == "Читаю": stats["reading"] = count
        elif db_status == "Прочитано": stats["finished"] = count
        elif db_status == "Приостановлено": stats["paused"] = count

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