from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime, date

class BookStatus(str, Enum):
    WANT_TO_READ = "WANT_TO_READ"      # Английские для API, в БД русские
    READING = "READING"
    FINISHED = "FINISHED"
    PAUSED = "PAUSED"

# Преобразование статусов API -> БД
def status_to_db(status: BookStatus) -> str:
    mapping = {
        BookStatus.WANT_TO_READ: "Хочу прочитать",
        BookStatus.READING: "Читаю",
        BookStatus.FINISHED: "Прочитано",
        BookStatus.PAUSED: "Приостановлено"
    }
    return mapping[status]

# Преобразование статусов БД -> API
def status_from_db(db_status: str) -> BookStatus:
    mapping = {
        "Хочу прочитать": BookStatus.WANT_TO_READ,
        "Читаю": BookStatus.READING,
        "Прочитано": BookStatus.FINISHED,
        "Приостановлено": BookStatus.PAUSED
    }
    return mapping.get(db_status, BookStatus.WANT_TO_READ)

# ---------- Модели для таблиц ----------

class ТипыКнигиBase(BaseModel):
    id_типа: str = ""                    # VARCHAR
    Название: str = ""

    class Config:
        from_attributes = True
        populate_by_name = True

class СерииBase(BaseModel):
    id_серии: str = ""                    # VARCHAR
    Название: str = ""
    Количество_книг: int = 0

    class Config:
        from_attributes = True
        populate_by_name = True

class АвторBase(BaseModel):
    id_автора: str = ""                    # VARCHAR (было int)
    Имя: str = ""
    Отчество: Optional[str] = ""
    Фамилия: Optional[str] = ""

    class Config:
        from_attributes = True
        populate_by_name = True

class ПроизведениеBase(BaseModel):
    id_произведения: str = ""              # VARCHAR (было int)
    Название: str = ""
    Описание: Optional[str] = ""
    Количество_страниц: int = 0

    class Config:
        from_attributes = True
        populate_by_name = True

class КнигаBase(BaseModel):
    id_книги: str = ""                      # VARCHAR (было int)
    Название: str = ""
    Автор: str = ""                          # Добавлено (из таблицы Книги)
    ISBN: Optional[str] = ""
    Количество_страниц: int = 0
    id_типа_книги: Optional[str] = None      # VARCHAR
    Язык: str = "Русский"
    Фото_обложки: Optional[str] = ""
    Описание: Optional[str] = ""              # Добавлено
    Жанр: Optional[str] = ""                  # Добавлено
    Штрих_код: Optional[str] = ""
    Серия_книг: bool = False
    год_издания: Optional[str] = ""           # VARCHAR в БД
    издательство: Optional[str] = ""

    class Config:
        from_attributes = True
        populate_by_name = True

class АккаунтBase(BaseModel):
    id_пользователя: str = ""                # VARCHAR
    Никнейм: str = ""                         # name в Kotlin
    Почта: str = ""                            # email в Kotlin
    Фото: Optional[str] = ""                   # avatarUrl в Kotlin
    Дата_регистрации: Optional[str] = ""       # joinedDate в Kotlin (String)
    reading_goal: int = 12                     # readingGoal
    pages_per_day_goal: int = 50               # pagesPerDayGoal

    class Config:
        from_attributes = True
        populate_by_name = True

class СессияСтатусBase(BaseModel):
    id_пользователя: str = ""                  # userId (VARCHAR)
    id_произведения: str = ""                   # VARCHAR (было int)
    Рейтинг: float = 0.0
    Статус: BookStatus = BookStatus.WANT_TO_READ
    current_page: int = 0
    review: str = ""
    start_date: Optional[str] = ""              # VARCHAR
    end_date: Optional[str] = ""                # VARCHAR
    added_date: Optional[str] = ""              # VARCHAR
    reading_time_minutes: int = 0

    class Config:
        from_attributes = True
        populate_by_name = True

    def to_db_status(self):
        """Преобразование статуса API в статус БД"""
        return status_to_db(self.Статус)

class ВишлистBase(BaseModel):
    id_книги: str = ""                          # VARCHAR
    id_пользователя: str = ""                   # VARCHAR
    дата_добавления: Optional[str] = ""         # VARCHAR
    приоритет: int = 1

    class Config:
        from_attributes = True
        populate_by_name = True

class СессияBase(BaseModel):
    id_сессии: str = ""                          # VARCHAR (было int)
    id_пользователя: str = ""                    # VARCHAR (было int)
    id_книги: str = ""                            # VARCHAR (добавлено)
    start_time: int = 0                           # для Kotlin ReadingSession
    end_time: int = 0
    pages_read: int = 0
    duration_minutes: int = 0
    Дата_начала: Optional[str] = ""               # VARCHAR
    Время_начала: Optional[str] = ""              # VARCHAR
    Начальная_страница: int = 0
    Последняя_страница: Optional[int] = None

    class Config:
        from_attributes = True
        populate_by_name = True

class ЦитатаBase(BaseModel):
    id_цитаты: str = ""                           # VARCHAR (было int)
    id_пользователя: str = ""                     # VARCHAR
    id_произведения: str = ""                     # VARCHAR
    Текст: str = ""
    Страница: Optional[int] = None
    Дата: Optional[str] = ""                       # VARCHAR
    chapter: Optional[str] = ""
    is_public: bool = True

    class Config:
        from_attributes = True
        populate_by_name = True

class ТэгBase(BaseModel):
    id_тэга: str = ""                              # VARCHAR
    Название: str = ""
    color: str = "#3498db"

    class Config:
        from_attributes = True
        populate_by_name = True

# ---------- Композитные модели для API ----------

class КнигаСАвтором(BaseModel):
    книга: КнигаBase
    авторы: List[АвторBase] = []

class КнигаСПрогрессом(BaseModel):
    книга: КнигаBase
    статус: СессияСтатусBase
    прогресс: float = 0.0

class СессияСтатусСКнигой(BaseModel):
    статус: СессияСтатусBase
    книга: КнигаBase
    произведение: ПроизведениеBase

class ПроизведениеСАвторами(BaseModel):
    произведение: ПроизведениеBase
    авторы: List[АвторBase] = []

class ЦитатаСТэгами(BaseModel):
    цитата: ЦитатаBase
    тэги: List[ТэгBase] = []

# ---------- Модели для соответствия Kotlin ----------

class KotlinBook(BaseModel):
    """Модель для отправки во фронтенд (соответствует Kotlin Book)"""
    id: str = ""
    title: str = ""
    author: str = ""
    coverUrl: str = ""  # Ссылка (опционально)
    coverData: str = ""  # 👈 НОВОЕ: base64 строка для фронта
    coverType: str = ""  # 👈 НОВОЕ: тип изображения
    description: str = ""
    pages: int = 0
    genre: str = ""
    isbn: str = ""
    publishedDate: str = ""
    publisher: str = ""

    @classmethod
    def from_db_book(cls, book: КнигаBase, authors: List[str] = None):
        """Преобразование из БД модели в Kotlin модель"""
        import base64

        # Конвертируем бинарные данные в base64 для отправки
        cover_data = ""
        if hasattr(book, 'Фото_данные') and book.Фото_данные:
            cover_data = base64.b64encode(book.Фото_данные).decode('utf-8')

        return cls(
            id=book.id_книги,
            title=book.Название,
            author=", ".join(authors) if authors else book.Автор,
            coverUrl=book.Фото_обложки or "",
            coverData=cover_data,
            coverType=book.Фото_тип or "",
            description=book.Описание or "",
            pages=book.Количество_страниц,
            genre=book.Жанр or "",
            isbn=book.ISBN or "",
            publishedDate=book.год_издания or "",
            publisher=book.издательство or ""
        )

class KotlinUserBook(BaseModel):
    """Модель для отправки во фронтенд (соответствует Kotlin UserBook)"""
    userId: str = ""
    bookId: str = ""
    status: BookStatus = BookStatus.WANT_TO_READ
    currentPage: int = 0
    rating: float = 0.0
    review: str = ""
    startDate: str = ""
    endDate: str = ""
    addedDate: str = ""
    readingTimeMinutes: int = 0

    @classmethod
    def from_db_status(cls, status: СессияСтатусBase, book_id: str):
        """Преобразование из БД статуса в Kotlin модель"""
        return cls(
            userId=status.id_пользователя,
            bookId=book_id,
            status=status.Статус,
            currentPage=status.current_page,
            rating=status.Рейтинг,
            review=status.review,
            startDate=status.start_date or "",
            endDate=status.end_date or "",
            addedDate=status.added_date or "",
            readingTimeMinutes=status.reading_time_minutes
        )

class KotlinUser(BaseModel):
    """Модель для отправки во фронтенд (соответствует Kotlin User)"""
    id: str = ""
    email: str = ""
    name: str = ""
    avatarUrl: str = ""
    readingGoal: int = 12
    joinedDate: str = ""
    pagesPerDayGoal: int = 50

    @classmethod
    def from_db_user(cls, user: АккаунтBase):
        """Преобразование из БД пользователя в Kotlin модель"""
        return cls(
            id=user.id_пользователя,
            email=user.Почта,
            name=user.Никнейм,
            avatarUrl=user.Фото or "",
            readingGoal=user.reading_goal,
            joinedDate=user.Дата_регистрации or "",
            pagesPerDayGoal=user.pages_per_day_goal
        )

class KotlinReadingSession(BaseModel):
    """Модель для отправки во фронтенд (соответствует Kotlin ReadingSession)"""
    id: str = ""
    userId: str = ""
    bookId: str = ""
    startTime: int = 0
    endTime: int = 0
    pagesRead: int = 0
    durationMinutes: int = 0

    @classmethod
    def from_db_session(cls, session: СессияBase):
        """Преобразование из БД сессии в Kotlin модель"""
        return cls(
            id=session.id_сессии,
            userId=session.id_пользователя,
            bookId=session.id_книги,
            startTime=session.start_time,
            endTime=session.end_time,
            pagesRead=session.pages_read,
            durationMinutes=session.duration_minutes
        )

class ApiBookWithProgress(BaseModel):
    """Модель для ответа API (соответствует Kotlin ApiBookWithProgress)"""
    book: KotlinBook
    userBook: KotlinUserBook
    progress: float = 0.0