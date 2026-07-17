from fastapi import APIRouter

from app.api.v1.public import athletes, clubs, coaches, competitions, news, rankings, reference

router = APIRouter(prefix="/public", tags=["public"])
router.include_router(athletes.router)
router.include_router(clubs.router)
router.include_router(coaches.router)
router.include_router(competitions.router)
router.include_router(news.router)
router.include_router(rankings.router)
router.include_router(reference.router)


@router.get("/ping")
def ping():
    """Проверочный health-check публичного API."""
    return {"status": "ok", "scope": "public"}
