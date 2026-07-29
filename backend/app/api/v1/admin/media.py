import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.api.v1.deps import require_role
from app.core.config import settings
from app.db.models.users import User

router = APIRouter(prefix="/media", tags=["admin:media"])

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_BYTES = 8 * 1024 * 1024  # 8 МБ — с запасом для фото с телефона

_configured = False


def _ensure_cloudinary_configured():
    """Ленивая настройка SDK — чтобы модуль импортировался даже если
    переменные окружения ещё не заданы (тогда просто вернём внятную
    ошибку по месту вызова, а не свалим импорт всего приложения)."""
    global _configured
    if _configured:
        return
    if not (settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET):
        raise HTTPException(
            status_code=503,
            detail=(
                "Загрузка фото не настроена: заполните CLOUDINARY_CLOUD_NAME/"
                "CLOUDINARY_API_KEY/CLOUDINARY_API_SECRET в переменных окружения бэкенда."
            ),
        )
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )
    _configured = True


@router.post("/upload")
async def upload_photo(
    file: UploadFile,
    _: User = Depends(require_role("super_admin", "admin", "editor")),
):
    """Принимает одну картинку (фото тренера/спортсмена и т.п.) и грузит её
    в Cloudinary. Возвращает {"url": "..."} — эту ссылку фронтенд кладёт
    прямо в photo_path, ничего больше хранить самим не нужно."""
    _ensure_cloudinary_configured()

    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Разрешены только JPEG, PNG или WebP")

    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=400, detail="Файл больше 8 МБ — выберите фото поменьше")

    try:
        result = cloudinary.uploader.upload(
            data,
            folder="atyrau-armwrestling/profiles",
            # Cloudinary сам подгонит под разумный максимум и уберёт лишний
            # вес — не нужно ресайзить фото на телефоне вручную.
            transformation=[{"width": 1200, "height": 1200, "crop": "limit", "quality": "auto"}],
        )
    except Exception as e:
        import logging
        logging.getLogger("uvicorn.error").error("Cloudinary upload: %s", e)
        raise HTTPException(status_code=502, detail="Ошибка загрузки файла в облачное хранилище")

    return {"url": result["secure_url"]}
