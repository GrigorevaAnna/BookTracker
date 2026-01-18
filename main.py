import uvicorn
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "BookTracker Backend работает!", "docs": "/docs"}

@app.get("/api/user/{user_id}/books")
def get_user_books(user_id: str):
    # Заглушка для теста
    return [
        {"id": "1", "title": "Тестовая книга", "progress": 0.5}
    ]

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"Сервер запущен на порту {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)