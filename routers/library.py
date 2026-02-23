from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Optional
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

router = APIRouter(prefix="/api", tags=["library"])


# ============================================
# 1. ВСЯ БИБЛИОТЕКА ПОЛЬЗОВАТЕЛЯ (с фильтром по статусу)
# ============================================
@router.get("/user/{user_id}/books", response_model=List[ApiBookWithProgress])
def get_user_books(
        user_id: str,
        status: Optional[BookStatus] = None,  # Если None - все книги
        db: Session = Depends(get_db)
):
    """
    Получить все книги пользователя с фильтром по статусу
    - Без status: все книги пользователя
    - С status=READING: только читаемые
    - С status=WANT_TO_READ: только вишлист
    - С status=FINISHED: только прочитанные
    """
    # Проверяем существование пользователя
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        return []  # Возвращаем пустой список, если пользователь не найден

    # Базовый запрос статусов пользователя
    query = db.query(Сессия_статус).filter(Сессия_статус.id_пользователя == user_id)

    # Фильтр по статусу (конвертируем API статус в статус БД)
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

        # Получаем авторов
        авторы = []
        труд = db.query(Труд).filter(Труд.id_произведения == произведение.id_произведения).all()
        for t in труд:
            автор = db.query(Авторы).filter(Авторы.id_автора == t.id_автора).first()
            if автор:
                автор_name = f"{автор.Имя} {автор.Фамилия or ''}".strip()
                авторы.append(автор_name)

        # Конвертируем в Kotlin модели
        kotlin_book = KotlinBook.from_db_book(книга, авторы)

        # Конвертируем статус
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


# ============================================
# 2. ТОЛЬКО КНИГИ В ВИШЛИСТЕ (WANT_TO_READ)
# ============================================
@router.get("/user/{user_id}/wishlist", response_model=List[ApiBookWithProgress])
def get_user_wishlist(
        user_id: str,
        db: Session = Depends(get_db)
):
    """Получить только книги из вишлиста пользователя"""
    return get_user_books(user_id, BookStatus.WANT_TO_READ, db)


# ============================================
# 3. ТОЛЬКО КНИГИ В ПРОЦЕССЕ ЧТЕНИЯ (READING)
# ============================================
@router.get("/user/{user_id}/reading", response_model=List[ApiBookWithProgress])
def get_user_reading(
        user_id: str,
        db: Session = Depends(get_db)
):
    """Получить только книги, которые пользователь сейчас читает"""
    return get_user_books(user_id, BookStatus.READING, db)


# ============================================
# 4. ТОЛЬКО ПРОЧИТАННЫЕ КНИГИ (FINISHED)
# ============================================
@router.get("/user/{user_id}/finished", response_model=List[ApiBookWithProgress])
def get_user_finished(
        user_id: str,
        db: Session = Depends(get_db)
):
    """Получить только прочитанные книги"""
    return get_user_books(user_id, BookStatus.FINISHED, db)


# ============================================
# 5. ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ
# ============================================
@router.get("/users/{user_id}", response_model=KotlinUser)
def get_user(
        user_id: str,
        db: Session = Depends(get_db)
):
    """Получить информацию о пользователе"""
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        # Возвращаем пользователя с ID, если не найден
        return KotlinUser(id=user_id)

    return KotlinUser.from_db_user(user)


# ============================================
# 6. ПОИСК КНИГ ПО НАЗВАНИЮ ИЛИ АВТОРУ
# ============================================
@router.get("/books/search", response_model=List[KotlinBook])
def search_books(
        query: str,
        db: Session = Depends(get_db)
):
    """Поиск книг по названию или автору"""
    if not query or len(query) < 2:
        return []

    search_pattern = f"%{query}%"

    # Ищем по названию книги
    книги = db.query(Книги).filter(
        or_(
            Книги.Название.ilike(search_pattern),
            Книги.Автор.ilike(search_pattern)
        )
    ).limit(20).all()

    result = []
    for книга in книги:
        # Получаем авторов для этой книги
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
                    if автор_name not in авторы:
                        авторы.append(автор_name)

        kotlin_book = KotlinBook.from_db_book(книга, авторы)
        result.append(kotlin_book)

    return result


# ============================================
# 7. ПОЛУЧЕНИЕ КОНКРЕТНОЙ КНИГИ
# ============================================
@router.get("/books/{book_id}", response_model=KotlinBook)
def get_book(
        book_id: str,
        db: Session = Depends(get_db)
):
    """Получить информацию о конкретной книге"""
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

    return KotlinBook.from_db_book(книга, авторы)


# ============================================
# 8. ДОБАВЛЕНИЕ КНИГИ В ВИШЛИСТ
# ============================================
@router.post("/user/{user_id}/wishlist/add/{book_id}")
def add_to_wishlist(
        user_id: str,
        book_id: str,
        db: Session = Depends(get_db)
):
    """Добавить книгу в вишлист пользователя"""
    # Проверяем существование пользователя
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Проверяем существование книги
    книга = db.query(Книги).filter(Книги.id_книги == book_id).first()
    if not книга:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    # Получаем произведение для этой книги
    содержание = db.query(Содержание).filter(
        Содержание.id_книги == book_id
    ).first()

    if not содержание:
        raise HTTPException(status_code=404, detail="Произведение не найдено")

    # Проверяем, нет ли уже в вишлисте
    existing = db.query(Вишлист).filter(
        and_(
            Вишлист.id_пользователя == user_id,
            Вишлист.id_книги == book_id
        )
    ).first()

    if existing:
        return {"message": "Книга уже в вишлисте"}

    # Добавляем в вишлист
    wishlist_item = Вишлист(
        id_пользователя=user_id,
        id_книги=book_id,
        дата_добавления=datetime.now().isoformat(),
        приоритет=1
    )
    db.add(wishlist_item)

    # Создаем запись в Сессия_статус
    status_item = Сессия_статус(
        id_пользователя=user_id,
        id_произведения=содержание.id_произведения,
        Статус=status_to_db(BookStatus.WANT_TO_READ),
        current_page=0,
        added_date=datetime.now().isoformat()
    )
    db.add(status_item)

    db.commit()

    return {"message": "Книга добавлена в вишлист"}


# ============================================
# 9. ОБНОВЛЕНИЕ СТАТУСА КНИГИ
# ============================================
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
    """Обновить статус книги (начать читать, закончить и т.д.)"""
    # Получаем произведение для книги
    содержание = db.query(Содержание).filter(
        Содержание.id_книги == book_id
    ).first()

    if not содержание:
        raise HTTPException(status_code=404, detail="Произведение не найдено")

    # Ищем существующий статус
    user_status = db.query(Сессия_статус).filter(
        and_(
            Сессия_статус.id_пользователя == user_id,
            Сессия_статус.id_произведения == содержание.id_произведения
        )
    ).first()

    if user_status:
        # Обновляем существующий
        user_status.Статус = status_to_db(status)
        if current_page is not None:
            user_status.current_page = current_page
        if rating is not None:
            user_status.Рейтинг = rating
        if review is not None:
            user_status.review = review

        # Если книга закончена
        if status == BookStatus.FINISHED:
            книга = db.query(Книги).filter(Книги.id_книги == book_id).first()
            if книга:
                user_status.current_page = книга.Количество_страниц
                user_status.end_date = datetime.now().isoformat()
    else:
        # Создаем новый статус
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
# 10. ПОЛУЧЕНИЕ СТАТИСТИКИ ПОЛЬЗОВАТЕЛЯ
# ============================================
@router.get("/user/{user_id}/stats")
def get_user_stats(
        user_id: str,
        db: Session = Depends(get_db)
):
    """Получить статистику чтения пользователя"""
    # Количество книг по статусам
    status_counts = db.query(
        Сессия_статус.Статус,
        db.func.count().label('count')
    ).filter(
        Сессия_статус.id_пользователя == user_id
    ).group_by(Сессия_статус.Статус).all()

    # Общее время чтения
    total_time = db.query(
        db.func.sum(Сессия_статус.reading_time_minutes)
    ).filter(
        Сессия_статус.id_пользователя == user_id
    ).scalar() or 0

    # Всего страниц прочитано
    total_pages = db.query(
        db.func.sum(Сессия_статус.current_page)
    ).filter(
        Сессия_статус.id_пользователя == user_id,
        Сессия_статус.Статус == 'Прочитано'
    ).scalar() or 0

    # Средний рейтинг
    avg_rating = db.query(
        db.func.avg(Сессия_статус.Рейтинг)
    ).filter(
        Сессия_статус.id_пользователя == user_id,
        Сессия_статус.Рейтинг > 0
    ).scalar() or 0

    stats = {
        "wishlist": 0,
        "reading": 0,
        "finished": 0,
        "paused": 0,
        "total_reading_time_minutes": total_time,
        "total_pages_read": total_pages,
        "average_rating": round(float(avg_rating), 1)
    }

    for status_row in status_counts:
        db_status = status_row[0]
        count = status_row[1]

        if db_status == "Хочу прочитать":
            stats["wishlist"] = count
        elif db_status == "Читаю":
            stats["reading"] = count
        elif db_status == "Прочитано":
            stats["finished"] = count
        elif db_status == "Приостановлено":
            stats["paused"] = count

    return stats