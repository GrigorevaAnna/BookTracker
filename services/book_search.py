# services/book_search.py
from typing import List, Dict, Any, Optional
import httpx


class CombinedSearchService:
    """Комбинированный поиск книг из внешних источников"""

    async def search_all(self, query: str, db=None) -> List[Dict[str, Any]]:
        """Поиск во всех внешних источниках"""
        results = []

        # Google Books
        google_results = await self._search_google_books(query)
        results.extend(google_results)

        # OpenLibrary
        openlib_results = await self._search_openlibrary(query)
        results.extend(openlib_results)

        # Удаляем дубликаты по ISBN
        unique_results = []
        seen_isbns = set()
        for book in results:
            if book.get("isbn") and book.get("isbn") not in seen_isbns:
                seen_isbns.add(book.get("isbn"))
                unique_results.append(book)
            elif not book.get("isbn"):
                unique_results.append(book)

        return unique_results

    async def _search_google_books(self, query: str) -> List[Dict[str, Any]]:
        """Поиск через Google Books API с фильтрацией по автору и названию"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://www.googleapis.com/books/v1/volumes",
                    params={"q": query, "maxResults": 30}
                )

                if response.status_code != 200:
                    return []

                data = response.json()
                results = []
                query_parts = query.lower().split()

                for item in data.get("items", []):
                    volume = item.get("volumeInfo", {})
                    title = volume.get("title", "")
                    authors = volume.get("authors", [])

                    # Строгая фильтрация
                    title_match = all(part in title.lower() for part in query_parts)
                    author_match = any(all(part in author.lower() for part in query_parts) for author in authors)

                    if title_match or author_match:
                        # Извлекаем обложку и преобразуем в прямую ссылку
                        images = volume.get("imageLinks", {})
                        cover_url = images.get("thumbnail", "")
                        cover_url = fix_cover_url(cover_url)  # 👈 ПРЕОБРАЗУЕМ

                        # Дополнительно: если нет обложки, пробуем сформировать вручную
                        if not cover_url and item.get("id"):
                            cover_url = f"https://books.google.com/books/content?id={item['id']}&printsec=frontcover&img=1&zoom=1&source=gbs_api"

                        results.append({
                            "title": title,
                            "author": ", ".join(authors) if authors else "Неизвестный автор",
                            "description": volume.get("description", ""),
                            "pages": volume.get("pageCount", 0),
                            "isbn": "",
                            "cover_url": cover_url,
                            "published_date": volume.get("publishedDate", ""),
                            "publisher": volume.get("publisher", ""),
                            "language": volume.get("language", ""),
                            "source": "Google Books"
                        })

                return results[:15]
        except Exception as e:
            print(f"Google Books ошибка: {e}")
            return []

    async def _search_openlibrary(self, query: str) -> List[Dict[str, Any]]:
        """Поиск через OpenLibrary API с фильтрацией по автору и названию"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://openlibrary.org/search.json",
                    params={"q": query, "limit": 30}
                )

                if response.status_code != 200:
                    return []

                data = response.json()
                results = []
                query_parts = query.lower().split()

                for doc in data.get("docs", []):
                    title = doc.get("title", "")
                    authors_list = doc.get("author_name", [])

                    title_match = all(part in title.lower() for part in query_parts)
                    author_match = any(all(part in author.lower() for part in query_parts) for author in authors_list)

                    if title_match or author_match:
                        cover_id = doc.get("cover_i", "")
                        cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else ""

                        results.append({
                            "title": title,
                            "author": ", ".join(authors_list) if authors_list else "Неизвестный автор",
                            "description": "",
                            "pages": doc.get("number_of_pages_median", 0),
                            "isbn": "",
                            "cover_url": cover_url,
                            "published_date": str(doc.get("first_publish_year", "")),
                            "publisher": doc.get("publisher", [""])[0] if doc.get("publisher") else "",
                            "language": doc.get("language", [""])[0] if doc.get("language") else "",
                            "source": "OpenLibrary"
                        })

                return results[:15]
        except Exception as e:
            print(f"OpenLibrary ошибка: {e}")
            return []


    def fix_cover_url(url: str) -> str:
        """Преобразует ссылку Google Books в прямую ссылку на изображение"""
        if not url:
            return ""

        # Ссылки Google Books
        if "books.google.com" in url:
            # Прямая ссылка на изображение через Google Books API
            # Извлекаем ID книги из URL
            if "id=" in url:
                import re
                match = re.search(r'id=([^&]+)', url)
                if match:
                    book_id = match.group(1)
                    # Используем прямую ссылку Google Books
                    return f"https://books.google.com/books/content?id={book_id}&printsec=frontcover&img=1&zoom=1&source=gbs_api"

        # Если ссылка уже прямая, возвращаем как есть
        return url


combined_search = CombinedSearchService()