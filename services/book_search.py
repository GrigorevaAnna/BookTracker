# services/book_search.py
from typing import Optional, Dict, Any, List
from services.google_books import google_books_service
from services.openlibrary import openlibrary_service


class BookSearchService:
    """Комбинированный сервис поиска книг"""

    async def search_by_isbn(self, isbn: str) -> Optional[Dict[str, Any]]:
        """Поиск по ISBN через несколько источников"""

        # 1. Пробуем OpenLibrary
        result = await openlibrary_service.search_by_isbn(isbn)
        if result:
            result["source"] = "openlibrary"
            return result

        # 2. Пробуем Google Books
        result = await google_books_service.search_by_isbn(isbn)
        if result:
            result["source"] = "google_books"
            return result

        return None

    async def search_by_title(self, title: str) -> List[Dict[str, Any]]:
        """Поиск по названию через несколько источников"""
        results = []

        # Пробуем OpenLibrary
        openlib_results = await openlibrary_service.search_by_title(title)
        for r in openlib_results:
            r["source"] = "openlibrary"
            results.append(r)

        # Пробуем Google Books
        google_results = await google_books_service.search_by_query(title)
        for r in google_results:
            # Избегаем дубликатов по ISBN
            if not any(existing.get("isbn") == r.get("isbn") for existing in results):
                r["source"] = "google_books"
                results.append(r)

        return results


book_search_service = BookSearchService()

