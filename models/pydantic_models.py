from pydantic import BaseModel
from typing import Optional
from enum import Enum

class BookStatus(str, Enum):
    WANT_TO_READ = "WANT_TO_READ"
    READING = "READING"
    FINISHED = "FINISHED"

class Book(BaseModel):
    id: str
    title: str
    author: str
    coverUrl: Optional[str] = ""
    description: Optional[str] = ""
    pages: int
    genre: Optional[str] = ""
    isbn: Optional[str] = ""
    publishedDate: Optional[str] = ""
    publisher: Optional[str] = ""

class UserBook(BaseModel):
    userId: str
    bookId: str
    status: BookStatus
    currentPage: int = 0
    rating: Optional[float] = None
    review: Optional[str] = None
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    addedDate: Optional[str] = None
    readingTimeMinutes: int = 0

class BookWithProgress(BaseModel):
    book: Book
    userBook: UserBook
    progress: float = 0.0