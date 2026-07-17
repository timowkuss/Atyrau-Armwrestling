from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router

app = FastAPI(
    title="Atyrau Armsport API",
    version="0.1.0",
    description=(
        "REST API федерации армрестлинга Атырау. Три группы маршрутов: "
        "/api/v1/public (сайт, без авторизации), /api/v1/admin (админ-панель "
        "сайта, JWT+роль), /api/v1/sync (только десктоп-приложение, "
        "service-token)."
    ),
)

# CORS для будущего React-фронтенда (Этап 4). На проде сузить allow_origins
# до реального домена сайта.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    "https://atyrau-armwrestling.vercel.app",
    "http://localhost:5173",
    ],
    allow_origin_regex=r"https://atyrau-armwrestling.*\.vercel\.app",  # чтобы preview/git-branch домены тоже работали
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
def health():
    return {"status": "ok"}
