"""Удаление фото из Cloudinary по запросу десктоп-приложения.

Десктоп не может удалять файлы в Cloudinary сам: unsigned upload preset
не поддерживает destroy, а CLOUDINARY_API_SECRET должен оставаться только
на бэкенде (см. services/cloudinary_photos.py). Поэтому, когда на десктопе
удаляется участник, чьё фото было загружено отдельно (папка турнира), он
шлёт сюда URL этого фото, и бэкенд вызывает delete_cloudinary_photo().
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.v1.deps import require_desktop_sync
from app.services.cloudinary_photos import delete_cloudinary_photo

router = APIRouter(prefix="/photos", tags=["sync:photos"])


class PhotoDeleteIn(BaseModel):
    url: str


@router.post("/delete")
def delete_photo(
    payload: PhotoDeleteIn,
    _: bool = Depends(require_desktop_sync),
):
    """Удаляет файл Cloudinary по его secure_url. Никогда не падает с
    4xx/5xx из-за самого файла — отсутствие/ошибка удаления просто
    логируется (см. delete_cloudinary_photo)."""
    delete_cloudinary_photo(payload.url)
    return {"status": "deleted"}
