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
    """Сервис рекомендаций книг через DeepSeek с умным кешированием"""

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
    # СБОР ДАННЫХ ДЛЯ ПРОМПТА
    # ================================================================

    def _build_prompt_data(self, liked_books, disliked_books, highly_rated_books):
        """Собирает данные для промпта"""
        user_likes = []
        for book in highly_rated_books:
            user_likes.append({
                "title": book['title'], "author": book['author'],
                "genre": book.get('genre', 'не указан'), "rating": book.get('rating', 0),
                "source": "высокая оценка"
            })
        for book in liked_books:
            if not any(b['title'] == book['title'] and b['author'] == book['author'] for b in user_likes):
                user_likes.append({
                    "title": book['title'], "author": book['author'],
                    "genre": book.get('genre', 'не указан'), "rating": 0,
                    "source": "понравилось"
                })

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

        # Обрезаем если слишком много
        likes_parts = likes_parts[:10]
        dislikes_parts = dislikes_parts[:10]
        library_list = sorted(books_in_library)[:15]

        return {
            "liked_text": "\n".join(likes_parts) if likes_parts else "Нет данных",
            "disliked_text": "\n".join(dislikes_parts) if dislikes_parts else "Нет",
            "library_text": "\n".join([f"📚 {b}" for b in library_list]) if library_list else "Нет",
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
        """Генерирует партию рекомендаций через DeepSeek"""

        if not self.api_key:
            print("❌ Нет API ключа DeepSeek")
            return self._get_fallback_recommendations(count)

        data = self._build_prompt_data(liked_books, disliked_books, highly_rated_books)

        print(f"\n{'='*60}")
        print(f"🎯 DEEPSEEK API (партия {batch_number}) | {user_id}")
        print(f"❤️{len(highly_rated_books)} 👍{len(liked_books)} 👎{len(data['user_dislikes'])} 📚{len(data['books_in_library'])}")
        print(f"{'='*60}\n")

        return await self._generate_via_deepseek(data, count, batch_number)

    async def _generate_via_deepseek(self, data: Dict, count: int, batch_number: int) -> Dict[str, Any]:
        """Генерация через DeepSeek с поддержкой JSON response"""

        system_prompt = f"""Ты — лучший книжный ассистент в мире. 

Твоя экспертиза:
- Ты досконально знаешь мировые бестселлеры, классику и самые громкие новинки
- Ты в курсе популярных книг из TikTok (BookTok), рекомендаций книжных блогеров
- Ты знаешь, какие книги получают премии и восторженные отзывы критиков
- Ты разбираешься в жанрах: young adult, dark romance, фэнтези, романтическая комедия, 
  психологическая драма, современная проза и других
- Ты знаешь популярных авторов: Ана Хуан, Эмма Скотт, Колин Гувер, Л. Дж. Шэн, 
  Бриттани Ш. Черри, Эрин Моргенштерн, Сара Дж. Маас, Ребекка Яррос, 
  Дженнифер Л. Арментроут, Елена Армас и многих других

Твоя задача — проанализировать вкусы пользователя и порекомендовать {count} новых книг.

ВАЖНЫЕ ПРАВИЛА:
1. ❤️ и 👍 = главный сигнал. Рекомендуй похожие по жанру, настроению, тропам
2. 👎 = анти-сигнал. НЕ рекомендуй эти книги и избегай похожих на них
3. 📚 = не показывай эти книги, но их жанры учитывай как интерес пользователя

КАЧЕСТВО:
- ТОЛЬКО реальные книги с рейтингом 4.0+ на Goodreads/LiveLib
- Учитывай новинки последних 2-3 лет
- Разнообразь: и хиты, и достойные менее известные книги

СТИЛЬ:
- Пиши живым, увлекательным языком (как книжный блогер)
- Описания должны быть заманчивыми, интригующими
- В reason указывай конкретные тропы и связь с любимыми книгами пользователя

Это партия №{batch_number}. Предложи НОВЫЕ книги (не из предыдущих партий).

❤️👍 ЧТО НРАВИТСЯ:
{data['liked_text']}

👎 ЧТО НЕ НРАВИТСЯ (избегай похожих):
{data['disliked_text']}

📚 В БИБЛИОТЕКЕ (не показывай, но жанры учитывай):
{data['library_text']}

Верни СТРОГО JSON (без markdown):
{{"comment": "персональный комментарий на русском", "books": [{{"title": "Название", "author": "Автор", "summary": "Описание 2-3 предложения", "genre": "Жанр", "reason": "Почему подходит"}}]}}"""

        try:
            print("📡 Отправляю запрос к DeepSeek API...")

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.api_url,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}"
                    },
                    json={
                        "model": "deepseek-chat",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": f"Порекомендуй мне {count} книг на основе моих предпочтений. Я хочу реально крутые, популярные книги, которые мне точно понравятся!"}
                        ],
                        "temperature": 0.7,
                        "max_tokens": 3000,
                        "response_format": {"type": "json_object"}
                    }
                )

                print(f"📥 Статус ответа: {response.status_code}")

                if response.status_code == 200:
                    data_resp = response.json()

                    usage = data_resp.get('usage', {})
                    print(f"💰 Токены: {usage.get('total_tokens', '?')} "
                          f"(запрос: {usage.get('prompt_tokens', '?')}, "
                          f"ответ: {usage.get('completion_tokens', '?')})")

                    content = data_resp['choices'][0]['message']['content']

                    # Парсим JSON
                    result = json.loads(content)
                    books_count = len(result.get('books', []))

                    print(f"✅ DeepSeek вернул {books_count} рекомендаций!")
                    print(f"💬 Комментарий: {result.get('comment', '')[:150]}...")

                    for i, book in enumerate(result.get('books', []), 1):
                        print(f"   {i}. {book.get('title')} — {book.get('author')}")
                        print(f"      Жанр: {book.get('genre')}")
                        print(f"      Почему: {book.get('reason', '')[:100]}...")

                    return result

                elif response.status_code == 402:
                    print("⚠️ DeepSeek: закончились бесплатные токены")
                    return self._get_fallback_recommendations(count)
                elif response.status_code == 429:
                    print("⚠️ DeepSeek: слишком много запросов")
                    return self._get_fallback_recommendations(count)
                else:
                    error_text = response.text[:300]
                    print(f"❌ DeepSeek ошибка {response.status_code}: {error_text}")
                    return self._get_fallback_recommendations(count)

        except httpx.ConnectError:
            print("❌ Ошибка подключения к DeepSeek API")
            return self._get_fallback_recommendations(count)
        except Exception as e:
            print(f"❌ DeepSeek ошибка: {type(e).__name__}: {e}")
            traceback.print_exc()
            return self._get_fallback_recommendations(count)

    def _get_fallback_recommendations(self, count: int = 5) -> Dict[str, Any]:
        """Запасные рекомендации"""
        all_books = [
            {"title": "Три тела", "author": "Лю Цысинь", "summary": "Научно-фантастический роман о первом контакте с инопланетной цивилизацией. Масштабная история, охватывающая десятилетия.", "genre": "Научная фантастика", "reason": "Глубокий научно-фантастический роман с масштабным миростроением."},
            {"title": "Песнь льда и пламени", "author": "Джордж Мартин", "summary": "Эпическая сага о борьбе за власть в мире, полном политических интриг, магии и драконов.", "genre": "Фэнтези", "reason": "Проработанный мир и сложные персонажи."},
            {"title": "Семь мужей Эвелин Хьюго", "author": "Тейлор Дженкинс Рейд", "summary": "История голливудской иконы, которая решается рассказать правду о своей жизни и семи браках.", "genre": "Романтическая проза", "reason": "Эмоциональная история о любви и выборе."},
            {"title": "Проект «Аве Мария»", "author": "Энди Вейер", "summary": "Астронавт просыпается на космическом корабле в миллионах километров от Земли.", "genre": "Научная фантастика", "reason": "Умная фантастика с юмором и наукой."},
            {"title": "Тайная история", "author": "Донна Тартт", "summary": "Группа студентов элитного колледжа погружается в мир античности и совершает убийство.", "genre": "Психологический триллер", "reason": "Напряжённый психологический роман."},
            {"title": "Ночной цирк", "author": "Эрин Моргенштерн", "summary": "Таинственный цирк появляется только ночью. Два иллюзиониста связаны магическим соревнованием.", "genre": "Магический реализм", "reason": "Атмосферное фэнтези с романтикой."},
            {"title": "Цветы для Элджернона", "author": "Дэниел Киз", "summary": "Умственно отсталый человек становится гением после научного эксперимента.", "genre": "Научная фантастика", "reason": "Глубокое философское произведение."},
            {"title": "Марсианин", "author": "Энди Вейер", "summary": "Астронавта забывают на Марсе. Используя науку и смекалку, он пытается выжить.", "genre": "Научная фантастика", "reason": "Оптимистичная фантастика с наукой."},
            {"title": "Щегол", "author": "Донна Тартт", "summary": "После взрыва в музее мальчик забирает картину. Эта кража определяет его жизнь.", "genre": "Современная проза", "reason": "Масштабная история об искусстве и искуплении."},
            {"title": "Жена путешественника во времени", "author": "Одри Ниффенеггер", "summary": "История любви человека, который непроизвольно путешествует во времени.", "genre": "Романтическая фантастика", "reason": "Уникальное сочетание фантастики и романтики."}
        ]
        print(f"📚 Запасные рекомендации ({min(count, len(all_books))} книг)")
        return {"comment": "На основе ваших предпочтений я подобрал эти книги.", "books": all_books[:count]}

    # ================================================================
    # УМНОЕ КЕШИРОВАНИЕ
    # ================================================================

    async def _filter_viewed_books(self, db: Session, user_id: str, books: List[Dict]) -> List[Dict]:
        """Убирает книги, на которые пользователь уже поставил реакцию"""
        from models.sql_models import Рекомендации_реакции

        reactions = db.query(Рекомендации_реакции).filter(
            Рекомендации_реакции.id_пользователя == user_id
        ).all()

        reacted_titles = {f"{r.title.lower()} — {r.author.lower()}" for r in reactions}

        filtered = []
        removed = 0
        for book in books:
            key = f"{book.get('title', '').lower()} — {book.get('author', '').lower()}"
            if key not in reacted_titles:
                filtered.append(book)
            else:
                removed += 1

        if removed:
            print(f"      🗑️ Удалено {removed} книг с реакциями, осталось {len(filtered)}")
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
            print(f"⚠️ Ошибка сохранения в кеш: {e}")
            db.rollback()

    async def _clean_viewed_from_cache(self, db: Session, user_id: str):
        """Удаляет просмотренные книги из ВСЕХ закешированных партий"""
        from models.sql_models import Кеш_рекомендаций, Рекомендации_реакции

        try:
            reactions = db.query(Рекомендации_реакции).filter(
                Рекомендации_реакции.id_пользователя == user_id
            ).all()
            if not reactions:
                return

            reacted_titles = {f"{r.title.lower()} — {r.author.lower()}" for r in reactions}

            cached_batches = db.query(Кеш_рекомендаций).filter(
                and_(
                    Кеш_рекомендаций.id_пользователя == user_id,
                    Кеш_рекомендаций.is_used == False,
                    Кеш_рекомендаций.expires_at > datetime.now()
                )
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
                print(f"🧹 Очищено {cleaned} просмотренных книг из кеша")
        except Exception as e:
            print(f"⚠️ Ошибка очистки кеша: {e}")
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

        if disliked_books is None:
            disliked_books = []
        if highly_rated_books is None:
            highly_rated_books = []

        lock = self._get_lock(user_id)

        async with lock:
            # Очищаем просроченный кеш
            db.query(Кеш_рекомендаций).filter(
                and_(Кеш_рекомендаций.id_пользователя == user_id, Кеш_рекомендаций.expires_at < datetime.now())
            ).delete()
            db.commit()

            # Проверяем кеш
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
                    unique_books = []
                    for book in all_books:
                        key = f"{book.get('title', '')} — {book.get('author', '')}"
                        if key not in seen:
                            seen.add(key)
                            unique_books.append(book)
                    result = {"comment": recommendations.get("comment", ""), "books": unique_books[:count], "from_cache": False, "refreshed": True}
                    self._save_to_cache(db, user_id, result, batch)
            else:
                recommendations = await self._generate_recommendations_batch(db, user_id, liked_books, disliked_books, highly_rated_books, count, batch)
                filtered_books = await self._filter_viewed_books(db, user_id, recommendations.get("books", []))
                result = {"comment": recommendations.get("comment", ""), "books": filtered_books if len(filtered_books) >= 3 else recommendations.get("books", []), "from_cache": False}
                self._save_to_cache(db, user_id, result, batch)

            # Предзагрузка следующей партии с задержкой
            next_batch = batch + 1
            if next_batch <= 10:
                next_cached = db.query(Кеш_рекомендаций).filter(
                    and_(Кеш_рекомендаций.id_пользователя == user_id, Кеш_рекомендаций.batch_number == next_batch,
                         Кеш_рекомендаций.expires_at > datetime.now())
                ).first()
                if not next_cached:
                    asyncio.create_task(
                        self._preload_with_delay(db, user_id, liked_books, disliked_books,
                                                  highly_rated_books, count, next_batch, delay=15)
                    )
                    print(f"🔄 Фоновая загрузка партии {next_batch} запланирована (через 15с)")

            # Обогащаем обложками
            enriched = await self.search_books_in_db(db, result)

            # Очищаем просмотренные из кеша
            await self._clean_viewed_from_cache(db, user_id)

            return {"recommendations": enriched, "has_more": batch < 10, "next_batch": next_batch if batch < 10 else None}

    async def _preload_with_delay(self, db, user_id, liked_books, disliked_books,
                                   highly_rated_books, count, batch_number, delay=15):
        """Фоновая загрузка с задержкой"""
        await asyncio.sleep(delay)
        await self._preload_next_batch(db, user_id, liked_books, disliked_books,
                                        highly_rated_books, count, batch_number)

    async def _preload_next_batch(self, db, user_id, liked_books, disliked_books, highly_rated_books, count, batch_number):
        from models.sql_models import Кеш_рекомендаций
        try:
            print(f"🔄 [ФОН] Готовлю партию {batch_number}...")
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
            print(f"✅ [ФОН] Партия {batch_number} готова! ({len(filtered_books)} книг)")
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
            enriched.append({
                "title": title, "author": author,
                "summary": book.get("summary", ""), "genre": book.get("genre", ""),
                "reason": book.get("reason", ""),
                "book_id": db_book.id_книги if db_book else None,
                "cover_url": cover_url or "", "in_library": db_book is not None
            })
        return {"comment": recommendations.get("comment", ""), "books": enriched}


recommendation_service = BookRecommendationService()