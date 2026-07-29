from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

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

# CORS — допускаем только нужные методы и заголовки
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    "https://atyrau-armwrestling.vercel.app",
    "http://localhost:5173",
    ],
    allow_origin_regex=r"https://atyrau-armwrestling.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Sync-Token"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


app.add_middleware(SecurityHeadersMiddleware)

app.include_router(api_router)


@app.get("/health")
def health():
    return {"status": "ok"}
