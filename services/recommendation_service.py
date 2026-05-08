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
from sqlalchemy import and_, func
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
    """Сервис рекомендаций книг: коллаборативная фильтрация + DeepSeek"""

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
    # КОЛЛАБОРАТИВНАЯ ФИЛЬТРАЦИЯ
    # ================================================================

    async def _get_collaborative_recommendations(
        self, db: Session, user_id: str, count: int = 5
    ) -> List[Dict]:
        """Рекомендации от похожих пользователей"""
        from models.sql_models import Сессия_статус, Произведения, Книги, Содержание, Авторы, Труд

        # Книги пользователя с высокими оценками
        user_high_rated = db.query(Сессия_статус.id_произведения).filter(
            and_(Сессия_статус.id_пользователя == user_id, Сессия_статус.Рейтинг >= 4.0)
        ).all()
        user_works = {row[0] for row in user_high_rated}

        if not user_works:
            return []

        # Похожие пользователи
        similar_users = db.query(Сессия_статус.id_пользователя).filter(
            and_(Сессия_статус.id_произведения.in_(user_works),
                 Сессия_статус.id_пользователя != user_id,
                 Сессия_статус.Рейтинг >= 4.0)
        ).distinct().all()
        similar_user_ids = [row[0] for row in similar_users]

        if not similar_user_ids:
            return []

        # Все книги пользователя (исключаем)
        all_user_books = db.query(Сессия_статус.id_произведения).filter(
            Сессия_статус.id_пользователя == user_id
        ).all()
        user_book_ids = {row[0] for row in all_user_books}

        # Рекомендованные книги
        recommended_works = db.query(
            Сессия_статус.id_произведения,
            func.count(Сессия_статус.id_пользователя).label('user_count'),
            func.avg(Сессия_статус.Рейтинг).label('avg_rating')
        ).filter(
            and_(Сессия_статус.id_пользователя.in_(similar_user_ids),
                 Сессия_статус.id_произведения.notin_(user_book_ids),
                 Сессия_статус.Рейтинг >= 4.0)
        ).group_by(Сессия_статус.id_произведения).order_by(
            func.count(Сессия_статус.id_пользователя).desc()
        ).limit(count * 2).all()

        books = []
        for work_row in recommended_works:
            work_id, user_count, avg_rating = work_row[0], work_row[1], float(work_row[2])

            work = db.query(Произведения).filter(Произведения.id_произведения == work_id).first()
            if not work:
                continue

            content = db.query(Содержание).filter(Содержание.id_произведения == work_id).first()
            if not content:
                continue

            book = db.query(Книги).filter(Книги.id_книги == content.id_книги).first()
            if not book:
                continue

            authors = db.query(Авторы).join(Труд).filter(Труд.id_произведения == work_id).all()
            author_str = ", ".join([f"{a.Имя} {a.Фамилия or ''}".strip() for a in authors]) or book.Автор

            books.append({
                "title": book.Название,
                "author": author_str,
                "summary": work.Описание or book.Описание or "",
                "genre": book.Жанр or "",
                "cover_url": book.Фото_обложки or "",
                "reason": f"Нравится {user_count} читателям с похожими вкусами (★{avg_rating:.1f})",
                "book_id": book.id_книги,
                "source": "collaborative",
                "verified": True
            })

            if len(books) >= count:
                break

        print(f"   👥 Коллаборативные: {len(books)} книг")
        return books[:count]


    # ================================================================
    # СБОР ДАННЫХ ДЛЯ ПРОМПТА
    # ================================================================

    def _build_prompt_data(self, liked_books, disliked_books, highly_rated_books):
        """Собирает данные для промпта"""
        user_likes = []
        favorite_authors = set()

        for book in highly_rated_books:
            user_likes.append({
                "title": book['title'], "author": book['author'],
                "genre": book.get('genre', 'не указан'), "rating": book.get('rating', 0),
                "source": "высокая оценка"
            })
            favorite_authors.add(book['author'])

        for book in liked_books:
            if not any(b['title'] == book['title'] and b['author'] == book['author'] for b in user_likes):
                user_likes.append({
                    "title": book['title'], "author": book['author'],
                    "genre": book.get('genre', 'не указан'), "rating": 0,
                    "source": "понравилось"
                })
                favorite_authors.add(book['author'])

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
                likes_parts.append(f"❤️ {book['title']} — {book['author']} (жанр: {book['genre']}, оценка: {book['rating']}/5)")
            else:
                likes_parts.append(f"👍 {book['title']} — {book['author']} (жанр: {book['genre']}, понравилось)")

        dislikes_parts = [f"👎 {b['title']} — {b['author']} (жанр: {b['genre']})" for b in user_dislikes]

        likes_parts = likes_parts[:10]
        dislikes_parts = dislikes_parts[:10]
        library_list = sorted(books_in_library)[:15]

        authors_list = sorted(favorite_authors)[:10]
        authors_text = "\n".join([f"⭐ {a}" for a in authors_list]) if authors_list else "Нет данных"

        return {
            "liked_text": "\n".join(likes_parts) if likes_parts else "Нет данных",
            "disliked_text": "\n".join(dislikes_parts) if dislikes_parts else "Нет",
            "library_text": "\n".join([f"📚 {b}" for b in library_list]) if library_list else "Нет",
            "favorite_authors": authors_text,
            "user_dislikes": user_dislikes[:10],
            "books_in_library": books_in_library
        }





    # ================================================================
    # ГЕНЕРАЦИЯ РЕКОМЕНДАЦИЙ
    # ================================================================

    async def _generate_recommendations_batch(
            self, db: Session, user_id: str,
            liked_books: List[Dict], disliked_books: List[Dict],
            highly_rated_books: List[Dict], count: int = 5, batch_number: int = 1
    ) -> Dict[str, Any]:
        """Двухуровневая система: коллаборативная → DeepSeek"""

        if not self.api_key:
            print("❌ Нет API ключа DeepSeek")
            return self._get_fallback_recommendations(count)

        data = self._build_prompt_data(liked_books, disliked_books, highly_rated_books)

        print(f"\n{'=' * 60}")
        print(f"🎯 ПАРТИЯ {batch_number} | {user_id}")
        print(f"{'=' * 60}\n")

        all_books = []

        # Шаг 1: Коллаборативная фильтрация
        print("👥 Шаг 1: Похожие пользователи...")
        collab_books = await self._get_collaborative_recommendations(db, user_id, count)
        all_books.extend(collab_books)
        print(f"   👥 Найдено: {len(collab_books)} книг")

        # Шаг 2: DeepSeek (если коллаборативных не хватило)
        if len(all_books) < count:
            needed = count - len(all_books)
            print(f"🤖 Шаг 2: DeepSeek ({needed} книг)...")
            deepseek_result = await self._generate_via_deepseek(data, needed, batch_number)

            for book in deepseek_result.get("books", []):
                if len(all_books) >= count:
                    break
                # Проверяем что такой книги ещё нет в all_books
                if not any(b['title'] == book.get('title') for b in all_books):
                    book["source"] = "deepseek"
                    all_books.append(book)

            print(f"   🤖 Добавлено от DeepSeek: {len(all_books) - len(collab_books)} книг")

        print(f"   🎯 Итого: {len(all_books)} книг\n")

        return {
            "comment": f"Подобрала для вас {len(all_books)} книг! Сначала — что нравится похожим читателям, затем — AI-рекомендации.",
            "books": all_books[:count]
        }

    async def _generate_via_deepseek(self, data: Dict, count: int, batch_number: int) -> Dict[str, Any]:
        """Генерация через DeepSeek"""

        system_prompt = f"""Ты — лучший книжный ассистент в мире. 

    ВСЕ ОТВЕТЫ ДОЛЖНЫ БЫТЬ НА РУССКОМ ЯЗЫКЕ!

    🎯 ТВОЯ ЗАДАЧА:
    Пользователь прочитал и полюбил определённые книги. Ты должен порекомендовать книги, 
    которые ЧАСТО ЧИТАЮТ ВМЕСТЕ с его любимыми книгами.

    📊 ЛОГИКА РЕКОМЕНДАЦИЙ:
    - Если человеку понравилось "Четвертое крыло", он почти наверняка полюбит "Из крови и пепла" и "Железное пламя"
    - Если понравилась "Гипотеза любви", рекомендуй "Испанский любовный обман" и другие nerdy romance
    - Если понравился "Жестокий принц", предложи "Королевство шипов и роз" 
    - Если понравилась Дюна — предложи "Гиперион" и "Три тела"

    Ты знаешь все читательские подборки, тренды BookTok, списки "если понравилось это, то читайте то".

    СТРОГИЕ ПРАВИЛА:
    - НЕ рекомендуй книги которые пользователь УЖЕ ЧИТАЛ (📚)
    - НЕ рекомендуй книги которые НЕ ПОНРАВИЛИСЬ (👎)
    - ТОЛЬКО реальные книги!

    ⭐ ЛЮБИМЫЕ АВТОРЫ (рекомендуй их другие книги):
    {data['favorite_authors']}

    ❤️👍 ЧТО НРАВИТСЯ (рекомендуй что читают вместе с этим):
    {data['liked_text']}

    👎 ЧТО НЕ НРАВИТСЯ (избегай):
    {data['disliked_text']}

    📚 В БИБЛИОТЕКЕ (не показывай):
    {data['library_text']}

    Верни СТРОГО JSON:
    {{"comment": "комментарий", "books": [{{"title": "Название", "author": "Автор", "summary": "Описание", "genre": "Жанр", "reason": "Почему читают вместе с ..."}}]}}"""

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.api_url,
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": "deepseek-chat",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user",
                             "content": f"Порекомендуй {count} книг, которые читают вместе с моими любимыми!"}
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







    # ================================================================
    # УМНОЕ КЕШИРОВАНИЕ
    # ================================================================

    async def _filter_viewed_books(self, db: Session, user_id: str, books: List[Dict]) -> List[Dict]:
        """Убирает ВСЕ книги которые уже показывались (из кеша и с реакциями)"""
        from models.sql_models import Рекомендации_реакции, Кеш_рекомендаций

        # 1. Книги с реакциями
        reactions = db.query(Рекомендации_реакции).filter(
            Рекомендации_реакции.id_пользователя == user_id
        ).all()
        reacted_titles = {f"{r.title.lower()} — {r.author.lower()}" for r in reactions}

        # 2. ВСЕ книги из кеша (не только used)
        all_cached = db.query(Кеш_рекомендаций).filter(
            Кеш_рекомендаций.id_пользователя == user_id
        ).all()

        cached_titles = set()
        for cached in all_cached:
            for b in (cached.books_json if isinstance(cached.books_json, list) else []):
                cached_titles.add(f"{b.get('title', '').lower()} — {b.get('author', '').lower()}")

        # 3. ВСЕ просмотренные
        all_viewed = reacted_titles | cached_titles

        filtered = []
        removed = 0
        for book in books:
            key = f"{book.get('title', '').lower()} — {book.get('author', '').lower()}"
            if key not in all_viewed:
                filtered.append(book)
            else:
                removed += 1

        if removed:
            print(f"      🗑️ Удалено {removed} уже показанных книг")
        return filtered





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
                filtered = [b for b in books if f"{b.get('title', '').lower()} — {b.get('author', '').lower()}" not in reacted_titles]
                if len(filtered) < original:
                    cached.books_json = filtered
                    cleaned += (original - len(filtered))
            if cleaned:
                db.commit()
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
                    recommendations = await self._generate_recommendations_batch(db, user_id, liked_books, disliked_books, highly_rated_books, count, batch)
                    all_books = filtered_books + recommendations.get("books", [])
                    seen = set()
                    unique = []
                    for book in all_books:
                        key = f"{book.get('title', '')} — {book.get('author', '')}"
                        if key not in seen:
                            seen.add(key)
                            unique.append(book)
                    result = {"comment": recommendations.get("comment", ""), "books": unique[:count]}
                    self._save_to_cache(db, user_id, result, batch)
            else:
                recommendations = await self._generate_recommendations_batch(db, user_id, liked_books, disliked_books,
                                                                             highly_rated_books, count, batch)
                filtered_books = await self._filter_viewed_books(db, user_id, recommendations.get("books", []))

            if not filtered_books and recommendations.get("books"):
                filtered_books = recommendations.get("books", [])
                print("      ⚠️ Все книги уже показаны, показываем заново")

            result = {"comment": recommendations.get("comment", ""), "books": filtered_books[:count]}
            self._save_to_cache(db, user_id, result, batch)






    async def _preload_with_delay(self, db, user_id, liked_books, disliked_books, highly_rated_books, count, batch_number, delay=15):
        await asyncio.sleep(delay)
        await self._preload_next_batch(db, user_id, liked_books, disliked_books, highly_rated_books, count, batch_number)






    async def _preload_next_batch(self, db, user_id, liked_books, disliked_books, highly_rated_books, count, batch_number):
        from models.sql_models import Кеш_рекомендаций
        try:
            recommendations = await self._generate_recommendations_batch(db, user_id, liked_books, disliked_books, highly_rated_books, count, batch_number)
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
            cover_url = db_book.Фото_обложки if db_book and db_book.Фото_обложки else await self._search_book_cover(title, author, i)
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


recommendation_service = BookRecommendationService()