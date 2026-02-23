from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
from routers.library import router as library_router

app = FastAPI(
    title="BookTracker API",
    description="Бэкенд для приложения BookTracker",
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

app.include_router(library_router)

@app.get("/")
def root():
    return {
        "message": "BookTracker API работает!",
        "docs": "/docs"
    }

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))  # Render даёт свой PORT
    uvicorn.run("main:app", host="0.0.0.0", port=port)