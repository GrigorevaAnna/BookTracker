from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from routers.library import router as library_router

app = FastAPI(
    title="BookTracker API",
    description="Бэкенд для приложения BookTracker с полной структурой БД",
    version="1.0.0"
)

# CORS для Android
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роуты
app.include_router(library_router)

@app.get("/")
def root():
    return {
        "message": "BookTracker API с полной структурой БД",
        "docs": "/docs"
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)