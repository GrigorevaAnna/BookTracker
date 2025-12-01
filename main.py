from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from routers.books import router as books_router

app = FastAPI(
    title="BookTracker API",
    description="Тестовый бэкенд для приложения BookTracker",
    version="1.0.0"
)

# CORS — чтобы Android мог подключаться
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роуты
app.include_router(books_router)

@app.get("/")
def root():
    return {"message": "BookTracker Backend работает!", "docs": "/docs"}

if __name__ == "__main__":
    print("="*60)
    print("БЭКЕНД ЗАПУЩЕН")
    print("Документация: http://127.0.0.1:8000/docs")
    print("Список книг:  http://127.0.0.1:8000/api/user/user_123/books")
    print("Дай этот адрес другому человеку (с твоим IP):")
    print("   http://ТОЙ_IP:8000/api/user/user_123/books")
    print("="*60)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)