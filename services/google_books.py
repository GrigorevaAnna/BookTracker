import httpx
from typing import Optional, Dict, Any, List
import asyncio


class GoogleBooksService:
    """Сервис для работы с Google Books API"""

    BASE_URL = "https://www.googleapis.com/books/v1/volumes"

    async def search_by_isbn(self, isbn: str) -> Optional[Dict[str, Any]]:
        """Поиск книги по ISBN"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    self.BASE_URL,
                    params={"q": f"isbn:{isbn}"}
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("totalItems", 0) > 0:
                        return self._parse_book_data(data["items"][0])
                return None

        except Exception as e:
            print(f"Ошибка при поиске по ISBN {isbn}: {e}")
            return None

    async def search_by_title_author(self, title: str, author: str = None) -> List[Dict[str, Any]]:
        """Поиск книг по названию и автору"""
        try:
            query = f"intitle:{title}"
            if author:
                query += f"+inauthor:{author}"

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    self.BASE_URL,
                    params={"q": query, "maxResults": 10}
                )

                if response.status_code == 200:
                    data = response.json()
                    results = []
                    for item in data.get("items", []):
                        results.append(self._parse_book_data(item))
                    return results
                return []

        except Exception as e:
            print(f"Ошибка при поиске книг: {e}")
            return []

    async def search_by_query(self, query: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """Общий поиск книг по любому запросу"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    self.BASE_URL,
                    params={"q": query, "maxResults": max_results}
                )

                if response.status_code == 200:
                    data = response.json()
                    results = []
                    for item in data.get("items", []):
                        results.append(self._parse_book_data(item))
                    return results
                return []

        except Exception as e:
            print(f"Ошибка при поиске: {e}")
            return []

    def _parse_book_data(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Парсинг данных книги из ответа Google Books API"""
        volume_info = item.get("volumeInfo", {})

        # Извлекаем авторов
        authors = volume_info.get("authors", [])
        author_str = ", ".join(authors) if authors else "Неизвестный автор"

        # Извлекаем обложку
        image_links = volume_info.get("imageLinks", {})
        cover_url = image_links.get("thumbnail", "")

        # Извлекаем ISBN
        industry_identifiers = volume_info.get("industryIdentifiers", [])
        isbn = ""
        for identifier in industry_identifiers:
            if identifier.get("type") in ["ISBN_13", "ISBN_10"]:
                isbn = identifier.get("identifier")
                break

        return {
            "title": volume_info.get("title", ""),
            "author": author_str,
            "description": volume_info.get("description", ""),
            "pages": volume_info.get("pageCount", 0),
            "published_date": volume_info.get("publishedDate", ""),
            "publisher": volume_info.get("publisher", ""),
            "isbn": isbn,
            "cover_url": cover_url,
            "language": volume_info.get("language", ""),
            "categories": volume_info.get("categories", []),
            "google_books_id": item.get("id", "")
        }


# Создаём экземпляр сервиса
google_books_service = GoogleBooksService()