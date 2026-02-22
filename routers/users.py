from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from models.pydantic_models import User
from models.sql_models import UserDB
from database.database import get_db

router = APIRouter(prefix="/api", tags=["users"])


@router.get("/users/{user_id}", response_model=User)
def get_user(
        user_id: str,
        db: Session = Depends(get_db)
):
    """Получить информацию о пользователе"""
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        # Возвращаем пустого пользователя если не найден (как во фронтенде)
        return User(id=user_id)

    return User(
        id=user.id,
        email=user.email,
        name=user.name,
        avatarUrl=user.avatar_url,
        readingGoal=user.reading_goal,
        joinedDate=user.joined_date,
        pagesPerDayGoal=user.pages_per_day_goal
    )