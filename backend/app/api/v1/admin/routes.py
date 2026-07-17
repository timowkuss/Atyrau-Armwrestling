from fastapi import APIRouter, Depends

from app.api.v1.admin import athletes, clubs, coaches, competitions, gallery, news
from app.api.v1.deps import require_role
from app.db.models.users import User

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(athletes.router)
router.include_router(clubs.router)
router.include_router(coaches.router)
router.include_router(news.router)
router.include_router(gallery.router)
router.include_router(competitions.router)


@router.get("/ping")
def ping(
    current_user: User = Depends(require_role("super_admin", "admin", "editor"))
):
    """Проверочный health-check с реальной проверкой роли."""
    return {"status": "ok", "scope": "admin", "role": current_user.role.code}
