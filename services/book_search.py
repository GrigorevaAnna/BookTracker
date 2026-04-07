import httpx
from typing import List, Dict, Any, Optional
import asyncio
from datetime import datetime


class CombinedBookSearchService:
    """Комбинированный сервис поиска книг из нескольких источников"""

    def __init__(self):
        self.timeout = 10.0

    async def search_google_books(self, query: str) -> List[Dict[str, Any]]:
        """Поиск через Google Books API"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    "https://www.googleapis.com/books/v1/volumes",
                    params={"q": query, "maxResults": 5}
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

                        results.append({
                            "title": volume.get("title", ""),
                            "author": ", ".join(authors) if authors else "Неизвестный автор",
                            "description": volume.get("description", ""),
                            "pages": volume.get("pageCount", 0),
                            "isbn": isbn,
                            "cover_url": cover_url,
                            "published_date": volume.get("publishedDate", ""),
                            "publisher": volume.get("publisher", ""),
                            "source": "Google Books",
                            "relevance": 90
                        })
                    return results
                return []
        except Exception as e:
            print(f"Google Books ошибка: {e}")
            return []

    async def search_openlibrary(self, query: str) -> List[Dict[str, Any]]:
        """Поиск через OpenLibrary API"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    "https://openlibrary.org/search.json",
                    params={"q": query, "limit": 5}
                )

                if response.status_code == 200:
                    data = response.json()
                    results = []
                    for doc in data.get("docs", []):
                        isbns = doc.get("isbn", [])
                        isbn = isbns[0] if isbns else ""

                        cover_id = doc.get("cover_i", "")
                        cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else ""

                        results.append({
                            "title": doc.get("title", ""),
                            "author": ", ".join(doc.get("author_name", [])),
                            "description": "",
                            "pages": doc.get("number_of_pages_median", 0),
                            "isbn": isbn,
                            "cover_url": cover_url,
                            "published_date": str(doc.get("first_publish_year", "")),
                            "publisher": doc.get("publisher", [""])[0] if doc.get("publisher") else "",
                            "source": "OpenLibrary",
                            "relevance": 85
                        })
                    return results
                return []
        except Exception as e:
            print(f"OpenLibrary ошибка: {e}")
            return []

    async def search_itunes(self, query: str) -> List[Dict[str, Any]]:
        """Поиск через Apple iTunes API (аудиокниги и книги)"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    "https://itunes.apple.com/search",
                    params={
                        "term": query,
                        "media": "ebook",
                        "limit": 5,
                        "country": "ru"
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    results = []
                    for item in data.get("results", []):
                        results.append({
                            "title": item.get("trackName", ""),
                            "author": item.get("artistName", ""),
                            "description": item.get("description", ""),
                            "pages": 0,  # iTunes не даёт количество страниц
                            "isbn": "",
                            "cover_url": item.get("artworkUrl100", "").replace("100x100", "600x600"),
                            "published_date": "",
                            "publisher": "",
                            "source": "Apple Books",
                            "relevance": 75
                        })
                    return results
                return []
        except Exception as e:
            print(f"Apple iTunes ошибка: {e}")
            return []

    async def search_fb2_library(self, query: str) -> List[Dict[str, Any]]:
        """Поиск через библиотеку FB2 (неофициальный API)"""
        # Это заглушка — можно подключить реальный API, если найдёте
        # Например: https://fb2.top/search?q=...
        # Или использовать локальную базу FB2
        return []

    async def search_local_db(self, query: str, db_session) -> List[Dict[str, Any]]:
        """Поиск в локальной базе данных (уже добавленные пользователями книги)"""
        from models.sql_models import Книги
        from sqlalchemy import or_

        try:
            books = db_session.query(Книги).filter(
                or_(
                    Книги.Название.ilike(f"%{query}%"),
                    Книги.Автор.ilike(f"%{query}%")
                )
            ).limit(5).all()

            results = []
            for book in books:
                # Конвертируем бинарные данные обложки в base64 для ответа
                cover_data = ""
                if book.Фото_данные:
                    import base64
                    cover_data = base64.b64encode(book.Фото_данные).decode('utf-8')

                results.append({
                    "title": book.Название,
                    "author": book.Автор,
                    "description": book.Описание or "",
                    "pages": book.Количество_страниц,
                    "isbn": book.ISBN or "",
                    "cover_url": book.Фото_обложки or "",
                    "cover_data": cover_data,
                    "published_date": book.год_издания or "",
                    "publisher": book.издательство or "",
                    "source": "Локальная база",
                    "relevance": 100,
                    "local_id": book.id_книги
                })
            return results
        except Exception as e:
            print(f"Локальная БД ошибка: {e}")
            return []

    async def search_all(self, query: str, db_session=None) -> List[Dict[str, Any]]:
        """
        Поиск во ВСЕХ источниках одновременно
        """
        print(f"🔍 Поиск книги: {query}")

        # Запускаем все поиски параллельно
        tasks = [
            self.search_google_books(query),
            self.search_openlibrary(query),
            self.search_itunes(query),
            self.search_fb2_library(query)
        ]

        # Добавляем поиск в локальной БД, если есть сессия
        if db_session:
            tasks.append(self.search_local_db(query, db_session))

        results_list = await asyncio.gather(*tasks)

        # Объединяем все результаты
        all_results = []
        for results in results_list:
            all_results.extend(results)

        # Удаляем дубликаты по названию + автору
        unique_results = []
        seen_keys = set()
        for book in all_results:
            key = f"{book['title'].lower()}_{book['author'].lower()}"
            if key not in seen_keys:
                seen_keys.add(key)
                unique_results.append(book)

        # Сортируем по релевантности
        unique_results.sort(key=lambda x: x.get('relevance', 0), reverse=True)

        return unique_results


# Создаём экземпляр сервиса
combined_search = CombinedBookSearchService()