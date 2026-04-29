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
        """Поиск через Google Books API"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://www.googleapis.com/books/v1/volumes",
                    params={"q": query, "maxResults": 10}
                )

                if response.status_code == 200:
                    data = response.json()
                    results = []
                    for item in data.get("items", []):
                        volume = item.get("volumeInfo", {})
                        authors = volume.get("authors", [])

                        # Извлекаем ISBN
                        isbn = ""
                        for identifier in volume.get("industryIdentifiers", []):
                            if identifier.get("type") in ["ISBN_13", "ISBN_10"]:
                                isbn = identifier.get("identifier")
                                break

                        # Извлекаем обложку
                        images = volume.get("imageLinks", {})
                        cover_url = images.get("thumbnail", "")

                        # Если есть ссылка на обложку, пробуем получить изображение
                        cover_data = None
                        cover_type = None
                        if cover_url:
                            try:
                                img_response = await client.get(cover_url)
                                if img_response.status_code == 200:
                                    cover_data = img_response.content
                                    cover_type = "image/jpeg"
                            except:
                                pass

                        results.append({
                            "title": volume.get("title", ""),
                            "author": ", ".join(authors) if authors else "Неизвестный автор",
                            "description": volume.get("description", ""),
                            "pages": volume.get("pageCount", 0),
                            "isbn": isbn,
                            "cover_url": cover_url,
                            "cover_data": cover_data,
                            "cover_type": cover_type,
                            "published_date": volume.get("publishedDate", ""),
                            "publisher": volume.get("publisher", ""),
                            "language": volume.get("language", ""),
                            "source": "Google Books"
                        })
                    return results
                return []
        except Exception as e:
            print(f"Google Books ошибка: {e}")
            return []

    async def _search_openlibrary(self, query: str) -> List[Dict[str, Any]]:
        """Поиск через OpenLibrary API"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://openlibrary.org/search.json",
                    params={"q": query, "limit": 10}
                )

                if response.status_code == 200:
                    data = response.json()
                    results = []
                    for doc in data.get("docs", []):
                        isbns = doc.get("isbn", [])
                        isbn = isbns[0] if isbns else ""

                        cover_id = doc.get("cover_i", "")
                        cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else ""

                        # Загружаем обложку
                        cover_data = None
                        cover_type = None
                        if cover_url:
                            try:
                                img_response = await client.get(cover_url)
                                if img_response.status_code == 200:
                                    cover_data = img_response.content
                                    cover_type = "image/jpeg"
                            except:
                                pass

                        results.append({
                            "title": doc.get("title", ""),
                            "author": ", ".join(doc.get("author_name", [])),
                            "description": "",
                            "pages": doc.get("number_of_pages_median", 0),
                            "isbn": isbn,
                            "cover_url": cover_url,
                            "cover_data": cover_data,
                            "cover_type": cover_type,
                            "published_date": str(doc.get("first_publish_year", "")),
                            "publisher": doc.get("publisher", [""])[0] if doc.get("publisher") else "",
                            "language": doc.get("language", [""])[0] if doc.get("language") else "",
                            "source": "OpenLibrary"
                        })
                    return results
                return []
        except Exception as e:
            print(f"OpenLibrary ошибка: {e}")
            return []


combined_search = CombinedSearchService()