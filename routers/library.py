from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional
from database.database import get_db
from models.sql_models import (
    Книги, Авторы, Произведения, Труд, Содержание,
    Аккаунты, Сессия_статус, Вишлист, Сессии, Цитаты
)
from models.pydantic_models import (
    КнигаBase, КнигаСАвтором, СессияСтатусBase,
    АккаунтBase, ЦитатаBase, BookStatus
)

router = APIRouter(prefix="/api", tags=["library"])


# Эндпоинт для получения книг пользователя с прогрессом
@router.get("/user/{user_id}/books", response_model=List[КнигаСАвтором])
def get_user_books(
        user_id: int,
        status: Optional[BookStatus] = None,
        db: Session = Depends(get_db)
):
    """Получить книги пользователя с фильтром по статусу"""

    # Получаем статусы чтения пользователя
    query = db.query(Сессия_статус).filter(Сессия_статус.id_пользователя == user_id)

    if status:
        query = query.filter(Сессия_статус.Статус == status.value)

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
                авторы.append(автор)

        # Создаем объект книги с авторами
        книга_с_автором = КнигаСАвтором(
            книга=КнигаBase.from_orm(книга),
            авторы=[АвторBase.from_orm(a) for a in авторы]
        )

        result.append(книга_с_автором)

    return result


# Эндпоинт для получения информации о пользователе
@router.get("/users/{user_id}", response_model=АккаунтBase)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


# Эндпоинт для поиска книг
@router.get("/books/search", response_model=List[КнигаСАвтором])
def search_books(
        query: str,
        db: Session = Depends(get_db)
):
    """Поиск книг по названию или автору"""

    # Ищем по названию книги
    книги = db.query(Книги).filter(Книги.Название.ilike(f"%{query}%")).all()

    # Ищем по автору
    авторы = db.query(Авторы).filter(
        (Авторы.Имя.ilike(f"%{query}%")) |
        (Авторы.Фамилия.ilike(f"%{query}%"))
    ).all()

    for автор in авторы:
        труд = db.query(Труд).filter(Труд.id_автора == автор.id_автора).all()
        for t in труд:
            содержание = db.query(Содержание).filter(
                Содержание.id_произведения == t.id_произведения
            ).first()
            if содержание:
                книга = db.query(Книги).filter(
                    Книги.id_книги == содержание.id_книги
                ).first()
                if книга and книга not in книги:
                    книги.append(книга)

    # Собираем результат с авторами
    result = []
    for книга in книги:
        авторы_книги = []
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
                if автор and автор not in авторы_книги:
                    авторы_книги.append(автор)

        книга_с_автором = КнигаСАвтором(
            книга=КнигаBase.from_orm(книга),
            авторы=[АвторBase.from_orm(a) for a in авторы_книги]
        )
        result.append(книга_с_автором)

    return result


# Эндпоинт для получения вишлиста пользователя
@router.get("/user/{user_id}/wishlist", response_model=List[КнигаСАвтором])
def get_wishlist(user_id: int, db: Session = Depends(get_db)):
    вишлист = db.query(Вишлист).filter(Вишлист.id_пользователя == user_id).all()

    result = []
    for item in вишлист:
        книга = db.query(Книги).filter(Книги.id_книги == item.id_книги).first()
        if книга:
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
                    if автор and автор not in авторы:
                        авторы.append(автор)

            книга_с_автором = КнигаСАвтором(
                книга=КнигаBase.from_orm(книга),
                авторы=[АвторBase.from_orm(a) for a in авторы]
            )
            result.append(книга_с_автором)

    return result


# Эндпоинт для получения цитат пользователя
@router.get("/user/{user_id}/quotes", response_model=List[ЦитатаBase])
def get_user_quotes(user_id: int, db: Session = Depends(get_db)):
    цитаты = db.query(Цитаты).filter(Цитаты.id_пользователя == user_id).all()
    return [ЦитатаBase.from_orm(q) for q in цитаты]


# Эндпоинт для обновления статуса чтения
@router.post("/user/{user_id}/book/{book_id}/status")
def update_book_status(
        user_id: int,
        book_id: int,
        status: BookStatus,
        current_page: Optional[int] = None,
        db: Session = Depends(get_db)
):
    # Находим произведение для книги
    содержание = db.query(Содержание).filter(Содержание.id_книги == book_id).first()
    if not содержание:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    # Обновляем или создаем статус
    статус = db.query(Сессия_статус).filter(
        and_(
            Сессия_статус.id_пользователя == user_id,
            Сессия_статус.id_произведения == содержание.id_произведения
        )
    ).first()

    if статус:
        статус.Статус = status.value
        if current_page is not None:
            статус.current_page = current_page
        статус.updated_at = func.now()
    else:
        статус = Сессия_статус(
            id_пользователя=user_id,
            id_произведения=содержание.id_произведения,
            Статус=status.value,
            current_page=current_page or 0
        )
        db.add(статус)

    db.commit()
    return {"message": "Статус обновлен"}