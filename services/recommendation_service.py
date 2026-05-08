# services/recommendation_service.py

import httpx
import json
import os
import re
import traceback
import asyncio
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from sqlalchemy import and_
from dotenv import load_dotenv

load_dotenv()

# 🔑 DEEPSEEK API
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

if DEEPSEEK_API_KEY:
    API_PROVIDER = "deepseek"
    API_KEY = DEEPSEEK_API_KEY
    print(f"🔑 DeepSeek API ключ: ✅ Найден")
    print("🌐 Используем DeepSeek (БЕСПЛАТНО, работает в России)")
else:
    API_PROVIDER = None
    API_KEY = None
    print("❌ DeepSeek API ключ не найден!")
    print("💡 Добавьте в .env: DEEPSEEK_API_KEY=sk-...")


def fix_cover_url(url: str) -> str:
    """Преобразует ссылку Google Books в прямую ссылку на изображение"""
    if not url:
        return url
    if "books.google.com" in url:
        if "books.google.com/books/content" in url:
            return url.replace("http://", "https://")
        if "id=" in url:
            match = re.search(r'id=([^&]+)', url)
            if match:
                book_id = match.group(1)
                return f"https://books.google.com/books/content?id={book_id}&printsec=frontcover&img=1&zoom=1&source=gbs_api"
    if url.startswith("http://"):
        url = url.replace("http://", "https://")
    return url


class BookRecommendationService:
    """Сервис рекомендаций книг через DeepSeek + Google Books фильтрация"""

    def __init__(self):
        self.provider = API_PROVIDER
        self.api_key = API_KEY
        self.api_url = DEEPSEEK_API_URL if self.api_key else None
        self._locks: Dict[str, asyncio.Lock] = {}

    def _get_lock(self, user_id: str) -> asyncio.Lock:
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]

    # ================================================================
    # ПОИСК ОБЛОЖЕК
    # ================================================================

    async def _search_book_cover(self, title: str, author: str, book_index: int = 0) -> Optional[str]:
        """Ищет обложку: Google Books → OpenLibrary → DuckDuckGo → Google Images"""
        print(f"      🔍 [{book_index}] Ищу обложку: {title[:50]}...")

        # Google Books API
        try:
            query = f"{title} {author}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://www.googleapis.com/books/v1/volumes",
                    params={"q": query, "maxResults": 5, "langRestrict": "ru"}
                )
                if response.status_code == 200:
                    data = response.json()
                    for item in data.get("items", []):
                        volume_info = item.get("volumeInfo", {})
                        book_title = volume_info.get("title", "").lower()
                        if title.lower() not in book_title and book_title not in title.lower():
                            if len(title) > 10:
                                continue
                        image_links = volume_info.get("imageLinks", {})
                        cover_url = (image_links.get("extraLarge") or
                                     image_links.get("large") or
                                     image_links.get("medium") or
                                     image_links.get("thumbnail") or
                                     image_links.get("smallThumbnail"))
                        if cover_url:
                            cover_url = fix_cover_url(cover_url)
                            print(f"         ✅ Google Books: {cover_url[:70]}...")
                            return cover_url
                        book_id = item.get("id")
                        if book_id:
                            cover_url = f"https://books.google.com/books/content?id={book_id}&printsec=frontcover&img=1&zoom=1&source=gbs_api"
                            print(f"         ✅ Google Books (ID): {cover_url[:70]}...")
                            return cover_url
        except Exception as e:
            print(f"         ⚠️ Google Books: {str(e)[:50]}")

        # OpenLibrary API
        try:
            query = f"{title} {author}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://openlibrary.org/search.json",
                    params={"q": query, "limit": 5}
                )
                if response.status_code == 200:
                    data = response.json()
                    for doc in data.get("docs", []):
                        doc_title = doc.get("title", "").lower()
                        if title.lower() not in doc_title and doc_title not in title.lower():
                            if len(title) > 10:
                                continue
                        cover_id = doc.get("cover_i")
                        if cover_id:
                            cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
                            print(f"         ✅ OpenLibrary: {cover_url[:70]}...")
                            return cover_url
                        isbn_list = doc.get("isbn", [])
                        if isbn_list:
                            cover_url = f"https://covers.openlibrary.org/b/isbn/{isbn_list[0]}-L.jpg"
                            print(f"         ✅ OpenLibrary (ISBN): {cover_url[:70]}...")
                            return cover_url
        except Exception as e:
            print(f"         ⚠️ OpenLibrary: {str(e)[:50]}")

        # DuckDuckGo Images
        try:
            query = f"{title} {author} book cover"
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1, "t": "booktracker"},
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                )
                if response.status_code == 200:
                    data = response.json()
                    image_url = data.get("Image", "")
                    if image_url and image_url.startswith("http"):
                        print(f"         ✅ DuckDuckGo: {image_url[:70]}...")
                        return image_url
        except Exception as e:
            print(f"         ⚠️ DuckDuckGo: {str(e)[:50]}")

        # Google Images
        try:
            query = f"{title} {author} книга обложка"
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"https://www.google.com/search?q={query}&tbm=isch&hl=ru",
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
                    }
                )
                if response.status_code == 200:
                    pattern = r'"ou":"(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"'
                    matches = re.findall(pattern, response.text)
                    for img_url in matches:
                        if any(x in img_url.lower() for x in ['icon', 'avatar', 'logo', 'favicon', '64x64', '32x32']):
                            continue
                        img_url = img_url.replace('\\u003d', '=').replace('\\u0026', '&')
                        if img_url.startswith("http"):
                            print(f"         ✅ Google Images: {img_url[:70]}...")
                            return img_url
        except Exception as e:
            print(f"         ⚠️ Google Images: {str(e)[:50]}")

        print(f"         ❌ Обложка не найдена")
        return None

    # ================================================================
    # GOOGLE BOOKS — ПОИСК НОВИНОК ПО ЖАНРУ
    # ================================================================

    async def _search_google_books_by_genre(self, genre: str, count: int = 3) -> List[Dict]:
        """Ищет книги в Google Books по КАТЕГОРИИ (жанру), а не по ключевым словам"""

        # Google Books категории на английском
        genre_subjects = {
            "Dark romance": "Fiction / Romance / Contemporary",
            "Городское фэнтези": "Fiction / Fantasy / Urban",
            "Психологический триллер": "Fiction / Thrillers / Psychological",
            "Романтическая комедия": "Fiction / Romance / Romantic Comedy",
            "Романтическая проза": "Fiction / Romance / Contemporary",
            "Фэнтези": "Fiction / Fantasy / Epic",
            "Научная фантастика": "Fiction / Science Fiction",
            "Магический реализм": "Fiction / Magical Realism",
            "Современная проза": "Fiction / Literary",
            "Тёмное фэнтези": "Fiction / Fantasy / Dark Fantasy",
            "Young adult": "Young Adult Fiction",
            "Детектив": "Fiction / Mystery & Detective",
        }

        subject = genre_subjects.get(genre, genre)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://www.googleapis.com/books/v1/volumes",
                    params={
                        "q": f'subject:"{subject}"',  # 👈 Ищем по КАТЕГОРИИ
                        "orderBy": "newest",
                        "maxResults": count * 2,
                        "printType": "books"
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    books = []

                    for item in data.get("items", []):
                        if len(books) >= count:
                            break

                        info = item.get("volumeInfo", {})
                        title = info.get("title", "")

                        if not title:
                            continue

                        authors = info.get("authors", ["Unknown"])
                        author_str = ", ".join(authors)

                        image_links = info.get("imageLinks", {})
                        cover = (image_links.get("thumbnail") or
                                 image_links.get("smallThumbnail") or "")
                        if cover:
                            cover = fix_cover_url(cover)

                        desc = info.get("description", "") or ""
                        if len(desc) > 300:
                            desc = desc[:300] + "..."

                        # Настоящие категории книги
                        categories = info.get("categories", [])
                        real_genre = ", ".join(categories[:2]) if categories else genre

                        books.append({
                            "title": title,
                            "author": author_str,
                            "summary": desc,
                            "genre": real_genre,  # 👈 Реальный жанр из Google Books
                            "cover_url": cover,
                            "published_date": info.get("publishedDate", ""),
                            "publisher": info.get("publisher", ""),
                            "reason": f"Новинка: {real_genre}",
                            "source": "google_books_new",
                            "verified": True
                        })

                    if books:
                        print(f"      📚 Google Books: {len(books)} книг в категории '{subject}'")
                    else:
                        # Если по subject не нашли — ищем по ключевым словам
                        print(f"      ⚠️ По subject не найдено, ищем по keywords...")
                        return await self._search_google_books_by_keywords(genre, count)

                    return books

        except Exception as e:
            print(f"      ⚠️ Google Books: {str(e)[:50]}")

        return []






    # ================================================================
    # СБОР ДАННЫХ ДЛЯ ПРОМПТА
    # ================================================================

    def _build_prompt_data(self, liked_books, disliked_books, highly_rated_books):
        """Собирает данные для промпта"""
        user_likes = []
        favorite_authors = set()
        favorite_genres = set()

        for book in highly_rated_books:
            user_likes.append({
                "title": book['title'], "author": book['author'],
                "genre": book.get('genre', 'не указан'), "rating": book.get('rating', 0),
                "source": "высокая оценка"
            })
            favorite_authors.add(book['author'])
            if book.get('genre'):
                favorite_genres.add(book['genre'])

        for book in liked_books:
            if not any(b['title'] == book['title'] and b['author'] == book['author'] for b in user_likes):
                user_likes.append({
                    "title": book['title'], "author": book['author'],
                    "genre": book.get('genre', 'не указан'), "rating": 0,
                    "source": "понравилось"
                })
                favorite_authors.add(book['author'])
                if book.get('genre'):
                    favorite_genres.add(book['genre'])

        user_dislikes = []
        for book in disliked_books:
            user_dislikes.append({
                "title": book['title'], "author": book['author'],
                "genre": book.get('genre', 'не указан')
            })

        books_in_library = set()
        for book in disliked_books:
            books_in_library.add(f"{book['title']} — {book['author']}")

        likes_parts = []
        for book in user_likes:
            if book['source'] == "высокая оценка":
                likes_parts.append(
                    f"❤️ {book['title']} — {book['author']} (жанр: {book['genre']}, оценка: {book['rating']}/5)")
            else:
                likes_parts.append(f"👍 {book['title']} — {book['author']} (жанр: {book['genre']}, понравилось)")

        dislikes_parts = [f"👎 {b['title']} — {b['author']} (жанр: {b['genre']})" for b in user_dislikes]

        likes_parts = likes_parts[:10]
        dislikes_parts = dislikes_parts[:10]
        library_list = sorted(books_in_library)[:15]

        authors_list = sorted(favorite_authors)[:10]
        authors_text = "\n".join([f"⭐ {a}" for a in authors_list]) if authors_list else "Нет данных"

        genres_list = sorted(favorite_genres)[:5]
        genres_text = ", ".join(genres_list) if genres_list else "не определены"

        return {
            "liked_text": "\n".join(likes_parts) if likes_parts else "Нет данных",
            "disliked_text": "\n".join(dislikes_parts) if dislikes_parts else "Нет",
            "library_text": "\n".join([f"📚 {b}" for b in library_list]) if library_list else "Нет",
            "favorite_authors": authors_text,
            "favorite_genres": genres_text,
            "favorite_genres_list": genres_list,
            "user_dislikes": user_dislikes[:10],
            "books_in_library": books_in_library
        }





    # ================================================================
    # ГЕНЕРАЦИЯ РЕКОМЕНДАЦИЙ ЧЕРЕЗ DEEPSEEK
    # ================================================================




    async def _generate_recommendations_batch(
            self, db: Session, user_id: str,
            liked_books: List[Dict], disliked_books: List[Dict],
            highly_rated_books: List[Dict], count: int = 5, batch_number: int = 1
    ) -> Dict[str, Any]:
        """Генерирует партию рекомендаций:
        - Нечётные партии (1,3,5...) → новинки из Google Books API
        - Чётные партии (2,4,6...) → рекомендации DeepSeek
        """

        if not self.api_key:
            print("❌ Нет API ключа DeepSeek")
            return self._get_fallback_recommendations(count)

        data = self._build_prompt_data(liked_books, disliked_books, highly_rated_books)

        # Определяем тип партии
        is_odd_batch = batch_number % 2 != 0  # 1, 3, 5, 7, 9 — нечётные → новинки Google Books

        print(f"\n{'=' * 60}")
        if is_odd_batch:
            print(f"🎯 GOOGLE BOOKS API (партия {batch_number}) | Новинки по жанрам")
        else:
            print(f"🎯 DEEPSEEK API (партия {batch_number}) | {user_id}")
        print(
            f"❤️{len(highly_rated_books)} 👍{len(liked_books)} 👎{len(data['user_dislikes'])} 📚{len(data['books_in_library'])}")
        print(f"🎯 Жанры: {data['favorite_genres']}")
        print(f"{'=' * 60}\n")

        if is_odd_batch:
            # Нечётные партии — новинки из Google Books
            return await self._generate_google_books_batch(data, count, batch_number)
        else:
            # Чётные партии — DeepSeek
            return await self._generate_via_deepseek(data, count, batch_number)






    async def _generate_via_deepseek(self, data: Dict, count: int, batch_number: int) -> Dict[str, Any]:
        """Генерация через DeepSeek"""

        system_prompt = f"""Ты — лучший книжный ассистент в мире. 

ВСЕ ОТВЕТЫ ДОЛЖНЫ БЫТЬ НА РУССКОМ ЯЗЫКЕ!

🎯 ПРИОРИТЕТ РЕКОМЕНДАЦИЙ:
1. СНАЧАЛА рекомендуй другие книги АВТОРОВ из списка ⭐
2. Затем — книги того же ЖАНРА ({data['favorite_genres']})
3. Затем — популярные новинки в любимых жанрах

СТРОГИЕ ПРАВИЛА:
- Рекомендуй ТОЛЬКО реально существующие книги
- Если сомневаешься — НЕ рекомендую
- НИКОГДА не придумывай книги

Это партия №{batch_number}.

⭐ ЛЮБИМЫЕ АВТОРЫ:
{data['favorite_authors']}

❤️👍 ЧТО НРАВИТСЯ:
{data['liked_text']}

👎 ЧТО НЕ НРАВИТСЯ:
{data['disliked_text']}

📚 В БИБЛИОТЕКЕ:
{data['library_text']}

Верни СТРОГО JSON:
{{"comment": "комментарий", "books": [{{"title": "Название", "author": "Автор", "summary": "Описание", "genre": "Жанр", "reason": "Почему"}}]}}"""

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.api_url,
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": "deepseek-chat",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": f"Порекомендуй {count} книг!"}
                        ],
                        "temperature": 0.7, "max_tokens": 3000,
                        "response_format": {"type": "json_object"}
                    }
                )
                if response.status_code == 200:
                    data_resp = response.json()
                    content = data_resp['choices'][0]['message']['content']
                    result = json.loads(content)
                    print(f"✅ DeepSeek: {len(result.get('books', []))} книг")
                    return result
                else:
                    print(f"❌ DeepSeek ошибка: {response.status_code}")
                    return self._get_fallback_recommendations(count)
        except Exception as e:
            print(f"❌ DeepSeek ошибка: {e}")
            return self._get_fallback_recommendations(count)

    def _get_fallback_recommendations(self, count: int = 5) -> Dict[str, Any]:
        all_books = [
            {"title": "Три тела", "author": "Лю Цысинь", "summary": "Первый контакт с инопланетной цивилизацией.",
             "genre": "Научная фантастика", "reason": "Масштабное миростроение."},
            {"title": "Песнь льда и пламени", "author": "Джордж Мартин", "summary": "Борьба за власть в фэнтези мире.",
             "genre": "Фэнтези", "reason": "Политические интриги."},
            {"title": "Семь мужей Эвелин Хьюго", "author": "Тейлор Дженкинс Рейд",
             "summary": "История голливудской иконы.", "genre": "Романтическая проза",
             "reason": "Эмоциональная история."},
            {"title": "Проект «Аве Мария»", "author": "Энди Вейер", "summary": "Астронавт спасает человечество.",
             "genre": "Научная фантастика", "reason": "Умная фантастика."},
            {"title": "Тайная история", "author": "Донна Тартт", "summary": "Студенты и убийство.",
             "genre": "Психологический триллер", "reason": "Напряжённый сюжет."}
        ]
        return {"comment": "На основе ваших предпочтений.", "books": all_books[:count]}

    # ================================================================
    # УМНОЕ КЕШИРОВАНИЕ
    # ================================================================

    async def _filter_viewed_books(self, db: Session, user_id: str, books: List[Dict]) -> List[Dict]:
        from models.sql_models import Рекомендации_реакции
        reactions = db.query(Рекомендации_реакции).filter(
            Рекомендации_реакции.id_пользователя == user_id
        ).all()
        reacted_titles = {f"{r.title.lower()} — {r.author.lower()}" for r in reactions}
        filtered = []
        for book in books:
            key = f"{book.get('title', '').lower()} — {book.get('author', '').lower()}"
            if key not in reacted_titles:
                filtered.append(book)
        return filtered

    def _save_to_cache(self, db: Session, user_id: str, result: Dict, batch: int):
        from models.sql_models import Кеш_рекомендаций
        try:
            cache_entry = Кеш_рекомендаций(
                id_пользователя=user_id,
                books_json=result.get("books", []),
                comment=result.get("comment", ""),
                batch_number=batch, is_used=True,
                expires_at=datetime.now() + timedelta(hours=24)
            )
            db.add(cache_entry)
            db.commit()
        except Exception as e:
            print(f"⚠️ Кеш: {e}")
            db.rollback()

    async def _clean_viewed_from_cache(self, db: Session, user_id: str):
        from models.sql_models import Кеш_рекомендаций, Рекомендации_реакции
        try:
            reactions = db.query(Рекомендации_реакции).filter(
                Рекомендации_реакции.id_пользователя == user_id
            ).all()
            if not reactions:
                return
            reacted_titles = {f"{r.title.lower()} — {r.author.lower()}" for r in reactions}
            cached_batches = db.query(Кеш_рекомендаций).filter(
                and_(Кеш_рекомендаций.id_пользователя == user_id,
                     Кеш_рекомендаций.is_used == False,
                     Кеш_рекомендаций.expires_at > datetime.now())
            ).all()
            cleaned = 0
            for cached in cached_batches:
                books = cached.books_json if isinstance(cached.books_json, list) else []
                original = len(books)
                filtered = [b for b in books if
                            f"{b.get('title', '').lower()} — {b.get('author', '').lower()}" not in reacted_titles]
                if len(filtered) < original:
                    cached.books_json = filtered
                    cleaned += (original - len(filtered))
            if cleaned:
                db.commit()
                print(f"🧹 Очищено {cleaned} книг из кеша")
        except Exception as e:
            print(f"⚠️ Очистка кеша: {e}")
            db.rollback()

    # ================================================================
    # ОСНОВНОЙ МЕТОД
    # ================================================================

    async def get_or_generate_recommendations(
            self, db: Session, user_id: str,
            liked_books: List[Dict], disliked_books: List[Dict] = None,
            highly_rated_books: List[Dict] = None, count: int = 5, batch: int = 1
    ) -> Dict[str, Any]:
        from models.sql_models import Кеш_рекомендаций
        if disliked_books is None: disliked_books = []
        if highly_rated_books is None: highly_rated_books = []
        lock = self._get_lock(user_id)

        async with lock:
            db.query(Кеш_рекомендаций).filter(
                and_(Кеш_рекомендаций.id_пользователя == user_id, Кеш_рекомендаций.expires_at < datetime.now())
            ).delete()
            db.commit()

            cached = db.query(Кеш_рекомендаций).filter(
                and_(Кеш_рекомендаций.id_пользователя == user_id, Кеш_рекомендаций.batch_number == batch,
                     Кеш_рекомендаций.is_used == False, Кеш_рекомендаций.expires_at > datetime.now())
            ).first()

            if cached:
                cached_books = cached.books_json if isinstance(cached.books_json, list) else []
                filtered_books = await self._filter_viewed_books(db, user_id, cached_books)
                if len(filtered_books) >= 3:
                    cached.books_json = filtered_books
                    cached.is_used = True
                    db.commit()
                    result = {"comment": cached.comment, "books": filtered_books, "from_cache": True}
                else:
                    cached.is_used = True
                    db.commit()
                    recommendations = await self._generate_recommendations_batch(db, user_id, liked_books,
                                                                                 disliked_books, highly_rated_books,
                                                                                 count, batch)
                    all_books = filtered_books + recommendations.get("books", [])
                    seen = set()
                    unique_books = []
                    for book in all_books:
                        key = f"{book.get('title', '')} — {book.get('author', '')}"
                        if key not in seen:
                            seen.add(key)
                            unique_books.append(book)
                    result = {"comment": recommendations.get("comment", ""), "books": unique_books[:count]}
                    self._save_to_cache(db, user_id, result, batch)
            else:
                recommendations = await self._generate_recommendations_batch(db, user_id, liked_books, disliked_books,
                                                                             highly_rated_books, count, batch)
                filtered_books = await self._filter_viewed_books(db, user_id, recommendations.get("books", []))
                result = {"comment": recommendations.get("comment", ""),
                          "books": filtered_books if len(filtered_books) >= 3 else recommendations.get("books", [])}
                self._save_to_cache(db, user_id, result, batch)

            next_batch = batch + 1
            if next_batch <= 10:
                next_cached = db.query(Кеш_рекомендаций).filter(
                    and_(Кеш_рекомендаций.id_пользователя == user_id, Кеш_рекомендаций.batch_number == next_batch,
                         Кеш_рекомендаций.expires_at > datetime.now())
                ).first()
                if not next_cached:
                    asyncio.create_task(
                        self._preload_with_delay(db, user_id, liked_books, disliked_books, highly_rated_books, count,
                                                 next_batch))

            enriched = await self.search_books_in_db(db, result)
            await self._clean_viewed_from_cache(db, user_id)
            return {"recommendations": enriched, "has_more": batch < 10,
                    "next_batch": next_batch if batch < 10 else None}

    async def _preload_with_delay(self, db, user_id, liked_books, disliked_books, highly_rated_books, count,
                                  batch_number, delay=15):
        await asyncio.sleep(delay)
        await self._preload_next_batch(db, user_id, liked_books, disliked_books, highly_rated_books, count,
                                       batch_number)

    async def _preload_next_batch(self, db, user_id, liked_books, disliked_books, highly_rated_books, count,
                                  batch_number):
        from models.sql_models import Кеш_рекомендаций
        try:
            recommendations = await self._generate_recommendations_batch(db, user_id, liked_books, disliked_books,
                                                                         highly_rated_books, count, batch_number)
            filtered_books = await self._filter_viewed_books(db, user_id, recommendations.get("books", []))
            cache_entry = Кеш_рекомендаций(
                id_пользователя=user_id,
                books_json=filtered_books if len(filtered_books) >= 3 else recommendations.get("books", []),
                comment=recommendations.get("comment", ""),
                batch_number=batch_number, is_used=False,
                expires_at=datetime.now() + timedelta(hours=24)
            )
            db.add(cache_entry)
            db.commit()
        except Exception as e:
            print(f"❌ [ФОН] Ошибка: {e}")
            db.rollback()







    async def search_books_in_db(self, db: Session, recommendations: Dict) -> Dict:
        from models.sql_models import Книги
        enriched = []
        for i, book in enumerate(recommendations.get("books", []), 1):
            title = book.get("title", "")
            author = book.get("author", "")
            db_book = db.query(Книги).filter(Книги.Название.ilike(f"%{title}%")).first()

            cover_url = None
            if db_book and db_book.Фото_обложки:
                cover_url = db_book.Фото_обложки
            else:
                cover_url = await self._search_book_cover(title, author, i)

            if db_book and cover_url and not db_book.Фото_обложки:
                db_book.Фото_обложки = cover_url
                db.commit()

            enriched.append({
                "title": title, "author": author,
                "summary": book.get("summary", ""), "genre": book.get("genre", ""),
                "reason": book.get("reason", ""),
                "book_id": db_book.id_книги if db_book else None,
                "cover_url": cover_url or "", "in_library": db_book is not None
            })
        return {"comment": recommendations.get("comment", ""), "books": enriched}







    async def _search_author_books_on_chitai_gorod(self, author: str, count: int = 3) -> List[Dict]:
        """
        Ищет книги автора на Читай-городе.
        Книги из магазина считаем проверенными — они точно существуют!
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    "https://www.chitai-gorod.ru/search",
                    params={"phrase": author},
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Accept": "text/html,application/xhtml+xml"
                    }
                )

                if response.status_code == 200:
                    html = response.text

                    # Ищем JSON с данными товаров (обычно в Next.js данных)
                    json_pattern = r'"(title|author|image|url)":"([^"]+)"'
                    matches = re.findall(json_pattern, html)

                    books = []
                    seen_titles = set()

                    # Парсим найденные книги
                    i = 0
                    while i < len(matches) - 2:
                        title = ""
                        book_author = ""
                        image = ""

                        if matches[i][0] == "title":
                            title = matches[i][1]
                        if i + 1 < len(matches) and matches[i + 1][0] == "author":
                            book_author = matches[i + 1][1]
                        if i + 2 < len(matches) and matches[i + 2][0] == "image":
                            image = matches[i + 2][1]

                        if title and title not in seen_titles and len(books) < count:
                            seen_titles.add(title)
                            books.append({
                                "title": title.replace("\\u0026", "&").replace("\\/", "/"),
                                "author": author,
                                "cover_url": image.replace("\\/", "/") if image else "",
                                "genre": "",
                                "summary": "",
                                "reason": f"Книга любимого автора {author} (Читай-город)",
                                "source": "chitai_gorod",
                                "verified": True  # ✅ Книги из магазина точно существуют!
                            })
                        i += 1

                    if books:
                        print(f"      📚 Читай-город: найдено {len(books)} книг автора '{author}'")

                    return books

        except Exception as e:
            print(f"      ⚠️ Читай-город: {str(e)[:50]}")

        return []


    async def _search_author_books(self, author: str, count: int = 3) -> List[Dict]:
        """
        Ищет книги автора через Google Books API.
        Гарантированно находит реальные книги!
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://www.googleapis.com/books/v1/volumes",
                    params={
                        "q": f'inauthor:"{author}"',
                        "maxResults": count + 3,  # Запрашиваем больше на случай фильтрации
                        "langRestrict": "ru",
                        "orderBy": "newest",
                        "printType": "books"
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    books = []
                    seen_titles = set()

                    for item in data.get("items", []):
                        if len(books) >= count:
                            break

                        info = item.get("volumeInfo", {})
                        title = info.get("title", "")

                        # Пропускаем дубликаты
                        if title.lower() in seen_titles:
                            continue
                        seen_titles.add(title.lower())

                        # Получаем авторов
                        authors_list = info.get("authors", [author])
                        author_str = ", ".join(authors_list)

                        # Обложка
                        image_links = info.get("imageLinks", {})
                        cover = (image_links.get("thumbnail") or
                                 image_links.get("smallThumbnail") or "")
                        if cover:
                            cover = fix_cover_url(cover)

                        # Жанры
                        genres = info.get("categories", [])
                        genre_str = ", ".join(genres[:3]) if genres else ""

                        # Описание
                        description = info.get("description", "") or ""
                        if len(description) > 300:
                            description = description[:300] + "..."

                        books.append({
                            "title": title,
                            "author": author_str,
                            "cover_url": cover,
                            "genre": genre_str,
                            "summary": description,
                            "published_date": info.get("publishedDate", ""),
                            "publisher": info.get("publisher", ""),
                            "isbn": info.get("industryIdentifiers", [{}])[0].get("identifier", ""),
                            "reason": f"Книга любимого автора {author}",
                            "source": "google_books_author",
                            "verified": True  # ✅ Из Google Books — точно существует!
                        })

                    if books:
                        print(f"      📚 Найдено {len(books)} книг автора '{author}'")

                    return books

        except Exception as e:
            print(f"      ⚠️ Поиск автора {author}: {str(e)[:50]}")

        return []

    async def _generate_google_books_batch(self, data: Dict, count: int, batch_number: int) -> Dict[str, Any]:
        """Генерирует партию новинок из Google Books с переводом на русский"""

        all_books = []
        genres = data.get("favorite_genres_list", [])

        if not genres:
            genres = ["fiction", "fantasy", "romance"]

        print(f"   📚 Ищу новинки в Google Books по жанрам: {', '.join(genres[:5])}")

        for genre in genres[:5]:
            if len(all_books) >= count:
                break

            new_books = await self._search_google_books_by_genre(genre, 3)

            for nb in new_books:
                if len(all_books) >= count:
                    break
                book_key = f"{nb['title']} — {nb['author']}"
                if book_key not in data.get('books_in_library', set()):
                    if not any(b['title'] == nb['title'] for b in all_books):
                        all_books.append(nb)

        # 👇 ПЕРЕВОДИМ НА РУССКИЙ
        if all_books:
            print(f"   🌐 Перевожу {len(all_books)} книг на русский...")
            all_books = await self._translate_books_to_russian(all_books)

        # Добираем если не хватает
        if len(all_books) < count:
            popular = await self._search_google_books_by_genre("bestseller", count - len(all_books))
            if popular:
                popular = await self._translate_books_to_russian(popular)
            for nb in popular:
                if len(all_books) >= count:
                    break
                if not any(b['title'] == nb['title'] for b in all_books):
                    all_books.append(nb)

        print(f"   ✅ Google Books: {len(all_books)} новинок (переведены)\n")

        return {
            "comment": f"Новинки в ваших любимых жанрах: {', '.join(genres[:3])}. Уже переведены на русский!",
            "books": all_books[:count]
        }


    async def _translate_books_to_russian(self, books: List[Dict]) -> List[Dict]:
        """Переводит названия и описания книг на русский через DeepSeek"""

        if not books:
            return books

        # Формируем список для перевода
        books_list = []
        for i, book in enumerate(books):
            books_list.append(
                f"{i + 1}. Title: {book.get('title', '')}\n"
                f"   Author: {book.get('author', '')}\n"
                f"   Description: {book.get('summary', '')[:200]}"
            )

        books_text = "\n\n".join(books_list)

        prompt = f"""Translate these book titles, author names, and descriptions into Russian.
    Make translations natural and appealing for Russian readers.
    
    {books_text}
    
    Return ONLY a JSON object with a "books" array:
    {{"books": [{{"title_ru": "...", "author_ru": "...", "summary_ru": "..."}}]}}"""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.api_url,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}"
                    },
                    json={
                        "model": "deepseek-chat",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": 2000,
                        "response_format": {"type": "json_object"}
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data['choices'][0]['message']['content']
                    result = json.loads(content)

                    translations = result.get("books", [])

                    for i, book in enumerate(books):
                        if i < len(translations):
                            tr = translations[i]
                            if tr.get("title_ru"):
                                book["title"] = tr["title_ru"]
                            if tr.get("author_ru"):
                                book["author"] = tr["author_ru"]
                            if tr.get("summary_ru"):
                                book["summary"] = tr["summary_ru"]

                    print(f"      🌐 Переведено {len(books)} книг на русский")

        except Exception as e:
            print(f"      ⚠️ Ошибка перевода: {str(e)[:50]}")

        return books





recommendation_service = BookRecommendationService()