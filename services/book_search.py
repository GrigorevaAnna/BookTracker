# services/book_search.py
from typing import List, Dict, Any, Optional
import httpx
import re


def fix_cover_url(url: str) -> str:
    """Преобразует ссылку Google Books в прямую ссылку на изображение"""
    if not url:
        return ""

    # Ссылки Google Books
    if "books.google.com" in url:
        # Прямая ссылка на изображение через Google Books API
        # Извлекаем ID книги из URL
        if "id=" in url:
            match = re.search(r'id=([^&]+)', url)
            if match:
                book_id = match.group(1)
                # Используем прямую ссылку Google Books
                return f"https://books.google.com/books/content?id={book_id}&printsec=frontcover&img=1&zoom=1&source=gbs_api"

    # Если ссылка уже прямая, возвращаем как есть
    return url


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

        # Удаляем дубликаты по названию и автору
        unique_results = []
        seen_keys = set()
        for book in results:
            key = f"{book.get('title', '')}_{book.get('author', '')}"
            if key not in seen_keys:
                seen_keys.add(key)
                unique_results.append(book)

        return unique_results

    async def _search_google_books(self, query: str) -> List[Dict[str, Any]]:
        """Поиск через Google Books API"""
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

                for item in data.get("items", []):
                    volume = item.get("volumeInfo", {})
                    title = volume.get("title", "")
                    authors = volume.get("authors", [])
                    description = volume.get("description", "")

                    # ============================================
                    # УЛУЧШЕННАЯ ФИЛЬТРАЦИЯ
                    # ============================================
                    query_lower = query.lower()
                    query_words = query_lower.split()

                    # Проверяем, содержит ли название все слова запроса
                    title_match = all(word in title.lower() for word in query_words)

                    # Проверяем, содержит ли автор все слова запроса
                    author_str = ", ".join(authors).lower()
                    author_match = all(word in author_str for word in query_words)

                    # Проверяем, является ли запрос отдельным словом в авторе
                    single_word_match = len(query_words) == 1 and query_lower in author_str

                    # Если запрос совпал с названием, автором или является частью имени автора
                    if title_match or author_match or single_word_match:
                        # Извлекаем ISBN
                        isbn = ""
                        for identifier in volume.get("industryIdentifiers", []):
                            if identifier.get("type") in ["ISBN_13", "ISBN_10"]:
                                isbn = identifier.get("identifier")
                                break

                        # Извлекаем обложку
                        images = volume.get("imageLinks", {})
                        cover_url = images.get("thumbnail", "")
                        if cover_url:
                            cover_url = fix_cover_url(cover_url)
                        elif item.get("id"):
                            cover_url = f"https://books.google.com/books/content?id={item['id']}&printsec=frontcover&img=1&zoom=1&source=gbs_api"

                        results.append({
                            "title": title,
                            "author": ", ".join(authors) if authors else "Неизвестный автор",
                            "description": description,
                            "pages": volume.get("pageCount", 0),
                            "isbn": isbn,
                            "cover_url": cover_url,
                            "published_date": volume.get("publishedDate", ""),
                            "publisher": volume.get("publisher", ""),
                            "language": volume.get("language", ""),
                            "source": "Google Books"
                        })

                # Возвращаем уникальные результаты (без дубликатов по названию)
                seen_titles = set()
                unique_results = []
                for r in results:
                    if r["title"].lower() not in seen_titles:
                        seen_titles.add(r["title"].lower())
                        unique_results.append(r)

                return unique_results[:15]
        except Exception as e:
            print(f"Google Books ошибка: {e}")
            return []

    async def _search_openlibrary(self, query: str) -> List[Dict[str, Any]]:
        """Поиск через OpenLibrary API"""
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
                query_lower = query.lower()
                query_words = query_lower.split()

                for doc in data.get("docs", []):
                    title = doc.get("title", "")
                    authors_list = doc.get("author_name", [])

                    title_match = all(word in title.lower() for word in query_words)
                    author_str = ", ".join(authors_list).lower()
                    author_match = all(word in author_str for word in query_words)
                    single_word_match = len(query_words) == 1 and query_lower in author_str

                    if title_match or author_match or single_word_match:
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

                seen_titles = set()
                unique_results = []
                for r in results:
                    if r["title"].lower() not in seen_titles:
                        seen_titles.add(r["title"].lower())
                        unique_results.append(r)

                return unique_results[:15]
        except Exception as e:
            print(f"OpenLibrary ошибка: {e}")
            return []


combined_search = CombinedSearchService()