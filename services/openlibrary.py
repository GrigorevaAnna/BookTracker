# services/openlibrary.py
import httpx
from typing import Optional, Dict, Any, List


class OpenLibraryService:
    """Сервис для работы с OpenLibrary API"""

    BASE_URL = "https://openlibrary.org/api/books"
    SEARCH_URL = "https://openlibrary.org/search.json"

    async def search_by_isbn(self, isbn: str) -> Optional[Dict[str, Any]]:
        """Поиск книги по ISBN через OpenLibrary"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    self.BASE_URL,
                    params={
                        "bibkeys": f"ISBN:{isbn}",
                        "format": "json",
                        "jscmd": "data"
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    key = f"ISBN:{isbn}"
                    if key in data:
                        return self._parse_book_data(data[key], isbn)
                return None

        except Exception as e:
            print(f"Ошибка при поиске по ISBN {isbn}: {e}")
            return None

    async def search_by_title(self, title: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Поиск книг по названию"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    self.SEARCH_URL,
                    params={"q": title, "limit": limit}
                )

                if response.status_code == 200:
                    data = response.json()
                    results = []
                    for doc in data.get("docs", []):
                        results.append(self._parse_search_result(doc))
                    return results
                return []

        except Exception as e:
            print(f"Ошибка при поиске книг: {e}")
            return []

    def _parse_book_data(self, data: Dict[str, Any], isbn: str) -> Dict[str, Any]:
        """Парсинг данных книги из ответа OpenLibrary"""
        # Извлекаем авторов
        authors = data.get("authors", [])
        author_names = [a.get("name", "") for a in authors if a.get("name")]
        author_str = ", ".join(author_names) if author_names else "Неизвестный автор"

        # Извлекаем обложку
        cover = data.get("cover", {})
        cover_url = cover.get("large", cover.get("medium", cover.get("small", "")))

        return {
            "title": data.get("title", ""),
            "author": author_str,
            "description": data.get("notes", ""),
            "pages": data.get("number_of_pages", 0),
            "published_date": data.get("publish_date", ""),
            "publisher": ", ".join(data.get("publishers", [])),
            "isbn": isbn,
            "cover_url": cover_url,
            "source": "openlibrary"
        }

    def _parse_search_result(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Парсинг результата поиска"""
        # Берём первый ISBN если есть
        isbns = doc.get("isbn", [])
        isbn = isbns[0] if isbns else ""

        # Формируем URL обложки
        cover_id = doc.get("cover_i", "")
        cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else ""

        return {
            "title": doc.get("title", ""),
            "author": ", ".join(doc.get("author_name", [])),
            "description": "",
            "pages": doc.get("number_of_pages_median", 0),
            "published_date": doc.get("first_publish_year", ""),
            "publisher": doc.get("publisher", [""])[0] if doc.get("publisher") else "",
            "isbn": isbn,
            "cover_url": cover_url,
            "source": "openlibrary"
        }


openlibrary_service = OpenLibraryService()