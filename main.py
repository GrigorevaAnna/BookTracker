import uvicorn
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.books import router as books_router

app = FastAPI(
    title="BookTracker API",
    description="Тестовый бэкенд для приложения BookTracker",
    version="1.0.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Для тестов. Можно указать конкретные домены
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
    port = int(os.environ.get("PORT", 10000))  # Render использует порт 10000
    print("="*60)
    print(f"БЭКЕНД ЗАПУЩЕН на порту {port}")
    print("="*60)
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)  # reload=False для продакшена