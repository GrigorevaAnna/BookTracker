from models.pydantic_models import Book, UserBook, BookStatus

# "Базы данных" в памяти
books_db: dict[str, Book] = {}
user_books_db: dict[tuple[str, str], UserBook] = {}

def init_sample_data():
    # Очищаем на всякий случай
    books_db.clear()
    user_books_db.clear()

    # Книги
    sample_books = [
        Book(id="1", title="Преступление и наказание", author="Фёдор Достоевский", pages=551, genre="Классика"),
        Book(id="2", title="1984", author="Джордж Оруэлл", pages=328, genre="Антиутопия"),
        Book(id="3", title="Мастер и Маргарита", author="Михаил Булгаков", pages=480, genre="Классика"),
        Book(id="4", title="Война и мир", author="Лев Толстой", pages=1225, genre="Классика"),
        Book(id="5", title="Дюна", author="Фрэнк Герберт", pages=412, genre="Фантастика"),
        Book(id="6", title="Гарри Поттер и философский камень", author="Дж. К. Роулинг", pages=399, genre="Фэнтези"),
    ]

    for book in sample_books:
        books_db[book.id] = book

    user_id = "user_123"
    connections = [
        ("1", BookStatus.FINISHED, 551, 5.0, "Шедевр!"),
        ("2", BookStatus.READING, 180, 0.0, ""),
        ("3", BookStatus.WANT_TO_READ, 0, 0.0, ""),
        ("4", BookStatus.READING, 800, 0.0, ""),
        ("5", BookStatus.WANT_TO_READ, 0, 0.0, ""),
        ("6", BookStatus.FINISHED, 399, 4.8, "Волшебство"),
    ]

    for conn in connections:
        book_id, status, current_page, rating, review = conn

        user_books_db[(user_id, book_id)] = UserBook(
            userId=user_id,
            bookId=book_id,
            status=status,
            currentPage=current_page,
            rating=rating,
            review=review
        )

# Автоматически загружаем при импорте
init_sample_data()