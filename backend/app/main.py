from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.session import SessionLocal


@asynccontextmanager
async def lifespan(app: FastAPI):
    """При старте пересчитываем агрегированную статистику спортсменов из
    фактических матчей и мест завершённых турниров. Это чинит данные уже
    завершённых турниров (например, после досыгранных вручную матчей) без
    ручного вмешательства. Сбой пересчёта не должен ронять приложение."""
    try:
        db = SessionLocal()
        try:
            from app.db.models.competitions import Competition
            from app.services.stats_engine import recalculate_all, record_elo_snapshots

            recalculate_all(db)
            completed_ids = [
                cid
                for (cid,) in db.query(Competition.id)
                .filter(Competition.status == "completed")
                .all()
            ]
            for cid in completed_ids:
                competition = db.get(Competition, cid)
                if competition is not None:
                    record_elo_snapshots(db, competition)
        finally:
            db.close()
    except Exception:
        pass
    yield


app = FastAPI(
    title="Atyrau Armsport API",
    version="0.1.0",
    description=(
        "REST API федерации армрестлинга Атырау. Три группы маршрутов: "
        "/api/v1/public (сайт, без авторизации), /api/v1/admin (админ-панель "
        "сайта, JWT+роль), /api/v1/sync (только десктоп-приложение, "
        "service-token)."
    ),
    lifespan=lifespan,
    # Swagger в проде не отдаём: он раскрывает полную карту эндпоинтов
    # потенциальному атакующему (в dev остаётся).
    docs_url=None if settings.ENVIRONMENT == "production" else "/docs",
    redoc_url=None if settings.ENVIRONMENT == "production" else "/redoc",
)

# CORS — только точные домены фронтенда, без regex: allow_origin_regex
# с жадным .* позволял любому задеплоить поддомен atyrau-armwrestling-*.
#vercel.app и получать отражённый Origin с credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://atyrau-armwrestling.vercel.app",
        "http://localhost:5173",
    ],
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Sync-Token"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # Referrer-Policy: API не отдаёт HTML, но заголовок защищает от
        # утечки токена в Referer при внешних переходах.
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # CSP: API отвечает JSON'ом, поэтому default-src 'none'. Swagger UI
        # (self-hosted в /docs) грузит скрипты/стили со своего CDN —
        # разрешаем только ему и только с 'unsafe-inline', без 'unsafe-eval'.
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; "
            "frame-ancestors 'none'; "
            "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
            "img-src 'self' data:; font-src 'self'"
        )
        return response


app.add_middleware(SecurityHeadersMiddleware)

app.include_router(api_router)


@app.get("/health")
def health():
    return {"status": "ok"}
