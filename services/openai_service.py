import httpx
import json
import os
import traceback
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


class BookRecommendationService:
    """Сервис рекомендаций книг через OpenAI"""

    def __init__(self):
        self.api_key = OPENAI_API_KEY
        print(f"🔑 OpenAI API Key загружен: {'✅' if self.api_key else '❌'}")
        if self.api_key:
            print(f"   Ключ начинается с: {self.api_key[:15]}...")

    async def get_recommendations(
            self,
            db: Session,
            user_id: str,
            liked_books: List[Dict[str, Any]],
            disliked_books: List[Dict[str, Any]] = None,
            highly_rated_books: List[Dict[str, Any]] = None,
            count: int = 5
    ) -> Dict[str, Any]:
        """
        Получить рекомендации книг от OpenAI на основе предпочтений пользователя
        """

        if disliked_books is None:
            disliked_books = []
        if highly_rated_books is None:
            highly_rated_books = []

        # Собираем книги, которые нравятся пользователю
        user_likes = []

        # 1. Книги с высокой оценкой
        for book in highly_rated_books:
            user_likes.append(
                f"{book['title']} — {book['author']} "
                f"(оценка: {book.get('rating', 'высокая')}, "
                f"жанр: {book.get('genre', 'не указан')})"
            )

        # 2. Понравившиеся из рекомендаций
        for book in liked_books:
            book_str = f"{book['title']} — {book['author']} (жанр: {book.get('genre', 'не указан')})"
            if book_str not in user_likes:
                user_likes.append(book_str)

        # Собираем книги, которые НЕ нравятся
        user_dislikes = []
        for book in disliked_books:
            user_dislikes.append(f"{book['title']} — {book['author']}")

        # Все взаимодействия (для исключения)
        all_interacted = set()
        for book in user_likes:
            # Берём только название и автора (без оценки и жанра)
            title_author = book.split(" (")[0]
            all_interacted.add(title_author)
        for book in user_dislikes:
            all_interacted.add(book)

        # Формируем промпт
        liked_text = "\n".join([
            f"{i + 1}. {book}" for i, book in enumerate(user_likes)
        ]) if user_likes else "Пока нет данных о предпочтениях"

        disliked_text = "\n".join([
            f"{i + 1}. {book}" for i, book in enumerate(user_dislikes)
        ]) if user_dislikes else "Нет"

        # Логируем, что отправляем
        print("\n" + "=" * 60)
        print(f"🎯 ЗАПРОС РЕКОМЕНДАЦИЙ ДЛЯ ПОЛЬЗОВАТЕЛЯ: {user_id}")
        print(f"📚 Высоко оценённых книг: {len(highly_rated_books)}")
        print(f"❤️  Понравилось рекомендаций: {len(liked_books)}")
        print(f"💔 Не понравилось: {len(disliked_books)}")
        print(f"📖 Всего книг в библиотеке: {len(all_interacted)}")
        print(f"🔢 Запрошено рекомендаций: {count}")
        print(f"📋 Первые 3 лайка: {user_likes[:3]}")
        print(f"📋 Первые 3 дизлайка: {user_dislikes[:3]}")
        print("=" * 60 + "\n")

        system_prompt = f"""You are a book recommendation assistant for a book tracking app.

Your task:
- Analyze books the user likes (high ratings + positive reactions)
- Analyze books the user dislikes
- Understand user's taste in genres, themes, writing style
- Recommend {count} new books the user will likely enjoy

CRITICAL RULES:
- NEVER recommend books from the user's library or previously interacted books
- Base recommendations on REAL, well-known books
- Be diverse but relevant
- Provide a brief personal comment explaining your choices
- Summaries must be 2-3 sentences, informative
- Each book must have a clear reason why it's recommended
- Write all responses in Russian language

USER LIKES:
{liked_text}

USER DISLIKES:
{disliked_text}

BOOKS TO AVOID (already in library or previously interacted):
{', '.join(sorted(list(all_interacted)[:50])) if all_interacted else 'None yet'}"""

        user_message = f"Порекомендуй {count} книг, которые могут мне понравиться. Объясни, почему каждая книга подходит под мой вкус."

        request_body = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.7,
            "max_tokens": 2000,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "book_recommendations",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "comment": {
                                "type": "string",
                                "description": "Персональный комментарий на русском языке"
                            },
                            "books": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "title": {
                                            "type": "string",
                                            "description": "Полное название книги"
                                        },
                                        "author": {
                                            "type": "string",
                                            "description": "Имя автора"
                                        },
                                        "summary": {
                                            "type": "string",
                                            "description": "Краткое описание на русском (2-3 предложения)"
                                        },
                                        "genre": {
                                            "type": "string",
                                            "description": "Основной жанр"
                                        },
                                        "reason": {
                                            "type": "string",
                                            "description": "Почему эта книга подходит пользователю (на русском)"
                                        }
                                    },
                                    "required": ["title", "author", "summary", "reason"]
                                }
                            }
                        },
                        "required": ["comment", "books"]
                    }
                }
            }
        }

        try:
            print("📡 Отправляю запрос к OpenAI API...")

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    OPENAI_API_URL,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}"
                    },
                    json=request_body
                )

                print(f"📥 Статус ответа: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()

                    # Логируем использование токенов
                    usage = data.get('usage', {})
                    print(f"💰 Токены: {usage.get('total_tokens', '?')} "
                          f"(prompt: {usage.get('prompt_tokens', '?')}, "
                          f"completion: {usage.get('completion_tokens', '?')})")

                    content = data['choices'][0]['message']['content']
                    print(f"📝 Ответ получен ({len(content)} символов)")

                    try:
                        result = json.loads(content)
                        books_count = len(result.get('books', []))
                        print(f"✅ Успешно! Получено {books_count} рекомендаций")
                        print(f"💬 Комментарий: {result.get('comment', '')[:100]}...")
                        return result

                    except json.JSONDecodeError as e:
                        print(f"❌ Ошибка парсинга JSON: {e}")
                        print(f"📄 Сырой ответ: {content[:500]}...")
                        return {
                            "comment": "Извините, не удалось обработать рекомендации.",
                            "books": []
                        }
                else:
                    error_text = response.text
                    print(f"❌ OpenAI API error {response.status_code}")
                    print(f"📄 Тело ошибки: {error_text[:500]}")

                    # Попытка распарсить ошибку
                    try:
                        error_json = response.json()
                        error_message = error_json.get('error', {}).get('message', error_text)
                        print(f"🔍 Сообщение ошибки: {error_message}")
                    except:
                        pass

                    return {
                        "comment": f"Сервис рекомендаций временно недоступен (ошибка {response.status_code}).",
                        "books": []
                    }

        except httpx.TimeoutException:
            print("❌ Таймаут запроса к OpenAI (60 секунд)")
            traceback.print_exc()
            return {
                "comment": "Сервис рекомендаций не ответил вовремя. Попробуйте позже.",
                "books": []
            }

        except Exception as e:
            print(f"❌ Ошибка запроса к OpenAI: {str(e)}")
            traceback.print_exc()
            return {
                "comment": "Произошла ошибка при получении рекомендаций.",
                "books": []
            }

    async def search_books_in_db(
            self,
            db: Session,
            recommendations: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Ищет рекомендованные книги в локальной БД"""
        from models.sql_models import Книги

        enriched_books = []

        for book in recommendations.get("books", []):
            title = book.get("title", "")
            author = book.get("author", "")

            # Ищем книгу в локальной БД
            db_book = db.query(Книги).filter(
                Книги.Название.ilike(f"%{title}%")
            ).first()

            book_data = {
                "title": title,
                "author": author,
                "summary": book.get("summary", ""),
                "genre": book.get("genre", ""),
                "reason": book.get("reason", ""),
                "book_id": db_book.id_книги if db_book else None,
                "cover_url": db_book.Фото_обложки if db_book else None,
                "in_library": db_book is not None
            }

            enriched_books.append(book_data)

        return {
            "comment": recommendations.get("comment", ""),
            "books": enriched_books
        }


recommendation_service = BookRecommendationService()