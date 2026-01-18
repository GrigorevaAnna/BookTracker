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
def read_root():
    return {"message": "API работает!"}

@app.get("/api/user/{user_id}/books")
def get_books(user_id: str):
    return [
        {"id": 1, "title": "Тестовая книга 1", "user_id": user_id},
        {"id": 2, "title": "Тестовая книга 2", "user_id": user_id}
    ]