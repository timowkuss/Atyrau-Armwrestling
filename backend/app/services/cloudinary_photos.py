"""Удаление фото в Cloudinary при замене/удалении карточки тренера или
спортсмена.

ВАЖНО: у Cloudinary нет "unsigned destroy" — удаление всегда требует
подписи запроса через CLOUDINARY_API_SECRET (в отличие от unsigned upload,
который безопасно использовать и с десктопа/фронта). Поэтому вся логика
удаления живёт ТОЛЬКО здесь, на бэкенде — секрет не должен попадать ни в
desktop-приложение, ни во фронтенд сайта.

Настройка (переменные окружения на сервере бэкенда):
    CLOUDINARY_CLOUD_NAME=<тот же cloud name, что и в unsigned preset>
    CLOUDINARY_API_KEY=<из Cloudinary Dashboard -> Settings -> API Keys>
    CLOUDINARY_API_SECRET=<оттуда же — держать в секрете>

Требует пакет cloudinary:  pip install cloudinary
"""

import logging
import os

import cloudinary
import cloudinary.uploader

logger = logging.getLogger(__name__)

_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "")
_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "")

_configured = bool(_CLOUD_NAME and _API_KEY and _API_SECRET)
if _configured:
    cloudinary.config(
        cloud_name=_CLOUD_NAME,
        api_key=_API_KEY,
        api_secret=_API_SECRET,
        secure=True,
    )


def _extract_public_id(url: str) -> str | None:
    """Достаёт public_id из обычной Cloudinary secure_url вида
    https://res.cloudinary.com/<cloud>/image/upload/v169.../coaches/photo2.jpg
    -> "coaches/photo2". Рассчитан на простую загрузку без трансформаций
    в URL (именно так грузит desktop-приложение — см. cloudinary_client.py).

    Удаляется только файл из собственного аккаунта: URL другого
    cloud name (чужой аккаунт/тестовое окружение) не распознаётся —
    десктоп не должен иметь возможности удалять что-либо в Cloudinary,
    кроме своих же загруженных фото."""
    if not url or "res.cloudinary.com" not in url:
        return None
    try:
        after_cloud = url.split("res.cloudinary.com/", 1)[1]
    except IndexError:
        return None
    cloud_name, _, rest = after_cloud.partition("/")
    if not rest or (cloud_name != _CLOUD_NAME and _CLOUD_NAME):
        return None
    try:
        after_upload = rest.split("/upload/", 1)[1]
    except IndexError:
        return None
    parts = after_upload.split("/")
    if parts and parts[0].startswith("v") and parts[0][1:].isdigit():
        parts = parts[1:]
    if not parts:
        return None
    public_id_with_ext = "/".join(parts)
    public_id, _, _ext = public_id_with_ext.rpartition(".")
    return public_id or public_id_with_ext


def delete_cloudinary_photo(url: str | None) -> None:
    """Удаляет фото по его Cloudinary URL. Никогда не бросает исключение
    наружу — неудачное удаление старого файла не должно мешать сохранению
    новых данных карточки (создать/обновить тренера/спортсмена важнее,
    чем гарантированно подчистить облако)."""
    if not url:
        return
    if not _configured:
        logger.warning(
            "CLOUDINARY_API_KEY/SECRET не заданы — старое фото %s не удалено", url
        )
        return
    public_id = _extract_public_id(url)
    if not public_id:
        logger.warning("Не удалось извлечь public_id из %s — пропускаю удаление", url)
        return
    try:
        cloudinary.uploader.destroy(public_id, invalidate=True)
    except Exception as e:
        logger.warning("Не удалось удалить старое фото %s (public_id=%s): %s", url, public_id, e)
