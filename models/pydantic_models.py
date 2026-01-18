from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

class BookStatus(str, Enum):
    WANT_TO_READ = "WANT_TO_READ"
    READING = "READING"
    FINISHED = "FINISHED"

class Book(BaseModel):
    id: str = Field(default="")
    title: str = Field(default="")
    author: str = Field(default="")
    coverUrl: str = Field(default="")
    description: str = Field(default="")
    pages: int = Field(default=0)
    genre: str = Field(default="")
    isbn: str = Field(default="")
    publishedDate: str = Field(default="")
    publisher: str = Field(default="")

class UserBook(BaseModel):
    userId: str = Field(default="")
    bookId: str = Field(default="")
    status: BookStatus = Field(default=BookStatus.WANT_TO_READ)
    currentPage: int = Field(default=0)
    rating: float = Field(default=0.0)
    review: str = Field(default="")
    startDate: str = Field(default="")
    endDate: str = Field(default="")
    addedDate: str = Field(default="")
    readingTimeMinutes: int = Field(default=0)

class BookWithProgress(BaseModel):
    book: Book
    userBook: UserBook
    progress: float = Field(default=0.0)