from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime

class BookStatus(str, Enum):
    WANT_TO_READ = "Хочу прочитать"
    READING = "Читаю"
    FINISHED = "Прочитано"
    PAUSED = "Приостановлено"

# Модели для ваших таблиц
class АккаунтBase(BaseModel):
    id_пользователя: str = ""
    Никнейм: str = ""
    Почта: str = ""
    Фото: Optional[str] = ""
    Дата_регистрации: Optional[datetime] = None

    class Config:
        from_attributes = True

class АвторBase(BaseModel):
    id_автора: int
    Имя: str = ""
    Отчество: Optional[str] = ""
    Фамилия: Optional[str] = ""

    class Config:
        from_attributes = True

class ПроизведениеBase(BaseModel):
    id_произведения: int
    Название: str = ""
    Описание: Optional[str] = ""
    Количество_страниц: int = 0

    class Config:
        from_attributes = True

class КнигаBase(BaseModel):
    id_книги: int
    Название: str = ""
    ISBN: Optional[str] = ""
    Количество_страниц: int = 0
    Язык: str = "Русский"
    Фото_обложки: Optional[str] = ""
    год_издания: Optional[int] = None
    издательство: Optional[str] = ""

    class Config:
        from_attributes = True

class КнигаСАвтором(BaseModel):
    книга: КнигаBase
    авторы: List[АвторBase] = []

class СессияСтатусBase(BaseModel):
    id_пользователя: str = ""
    id_произведения: int
    Рейтинг: float = 0.0
    Статус: BookStatus = BookStatus.WANT_TO_READ
    current_page: int = 0
    review: str = ""
    reading_time_minutes: int = 0

    class Config:
        from_attributes = True

class СессияBase(BaseModel):
    id_сессии: int
    id_пользователя: int
    id_произведения: int
    Дата_начала: datetime
    Начальная_страница: int
    Последняя_страница: Optional[int] = None

    class Config:
        from_attributes = True

class ЦитатаBase(BaseModel):
    id_цитаты: int
    Текст: str
    Страница: Optional[int] = None
    Дата: Optional[datetime] = None

    class Config:
        from_attributes = True

class КнигаСПрогрессом(BaseModel):
    книга: КнигаBase
    статус: СессияСтатусBase
    прогресс: float = 0.0