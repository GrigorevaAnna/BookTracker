from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from models.pydantic_models import KotlinUser
from models.sql_models import Аккаунты
from database.database import get_db

router = APIRouter(prefix="/api", tags=["users"])


@router.get("/users/{user_id}", response_model=KotlinUser)
def get_user(
        user_id: str,
        db: Session = Depends(get_db)
):
    """Получить информацию о пользователе"""
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        # Возвращаем пользователя только с ID если не найден
        return KotlinUser(id=user_id)

    return KotlinUser(
        id=user.id_пользователя,
        email=user.Почта,
        name=user.Никнейм,
        avatarUrl=user.Фото or "",
        readingGoal=user.reading_goal,
        joinedDate=user.Дата_регистрации or "",
        pagesPerDayGoal=user.pages_per_day_goal
    )


@router.get("/users/{user_id}/stats")
def get_user_stats(
        user_id: str,
        db: Session = Depends(get_db)
):
    """Получить статистику пользователя"""
    from models.sql_models import Сессия_статус

    # Проверяем пользователя
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Количество книг по статусам
    stats = {
        "wishlist": 0,
        "reading": 0,
        "finished": 0,
        "paused": 0,
        "total_pages": 0,
        "total_reading_time": 0,
        "average_rating": 0.0
    }

    # Получаем статистику из Сессия_статус
    status_counts = db.query(
        Сессия_статус.Статус,
        db.func.count().label('count'),
        db.func.sum(Сессия_статус.current_page).label('total_pages'),
        db.func.sum(Сессия_статус.reading_time_minutes).label('total_time'),
        db.func.avg(Сессия_статус.Рейтинг).label('avg_rating')
    ).filter(
        Сессия_статус.id_пользователя == user_id
    ).group_by(Сессия_статус.Статус).all()

    for row in status_counts:
        status, count, pages, time, rating = row
        if status == "Хочу прочитать":
            stats["wishlist"] = count
        elif status == "Читаю":
            stats["reading"] = count
            stats["total_pages"] += pages or 0
            stats["total_reading_time"] += time or 0
        elif status == "Прочитано":
            stats["finished"] = count
            stats["total_pages"] += pages or 0
            stats["total_reading_time"] += time or 0
            if rating:
                stats["average_rating"] = round(float(rating), 1)
        elif status == "Приостановлено":
            stats["paused"] = count

    return stats


@router.put("/users/{user_id}/profile")
def update_user_profile(
        user_id: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
        avatarUrl: Optional[str] = None,
        readingGoal: Optional[int] = None,
        pagesPerDayGoal: Optional[int] = None,
        db: Session = Depends(get_db)
):
    """Обновить профиль пользователя"""
    user = db.query(Аккаунты).filter(Аккаунты.id_пользователя == user_id).first()

    if not user:
        # Создаем нового пользователя, если не существует
        user = Аккаунты(
            id_пользователя=user_id,
            Никнейм=name or f"User_{user_id}",
            Почта=email or f"{user_id}@example.com",
            Пароль="temp_password",  # В реальном приложении должен быть хэш
            Фото=avatarUrl,
            Дата_регистрации=datetime.now().isoformat(),
            reading_goal=readingGoal or 12,
            pages_per_day_goal=pagesPerDayGoal or 50
        )
        db.add(user)
    else:
        # Обновляем существующего
        if name is not None:
            user.Никнейм = name
        if email is not None:
            user.Почта = email
        if avatarUrl is not None:
            user.Фото = avatarUrl
        if readingGoal is not None:
            user.reading_goal = readingGoal
        if pagesPerDayGoal is not None:
            user.pages_per_day_goal = pagesPerDayGoal
        user.updated_at = datetime.now()

    db.commit()

    return {"message": "Профиль обновлен"}