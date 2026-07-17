from fastapi import APIRouter, Depends

from app.api.v1.deps import require_desktop_sync
from app.api.v1.sync import athletes, categories, competitions, matches

router = APIRouter(prefix="/sync", tags=["sync"])
router.include_router(athletes.router)
router.include_router(categories.router)
router.include_router(competitions.router)
router.include_router(matches.router)

@router.get("/ping")
def ping(_: bool = Depends(require_desktop_sync)):
    """Проверочный health-check для десктоп-приложения."""
    return {"status": "ok", "scope": "sync"}
