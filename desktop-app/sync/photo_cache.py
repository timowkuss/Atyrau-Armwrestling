"""Единая точка получения ЛОКАЛЬНОГО файла для показа фото в интерфейсе.

photo_path в БД теперь бывает двух видов:
  1. Cloudinary URL (https://res.cloudinary.com/...) — все новые фото,
     а также любые фото, подтянутые с сайта через pull_sync.
  2. Старый локальный путь (photos/ivan.jpg) — записи, сохранённые ДО
     перехода на Cloudinary. Их никто не мигрирует принудительно, чтобы
     не потерять фото, у которых на сайте могло не быть аналога.

Все места в armwrestling_tournament.py, где раньше было
    Path(x["photo_path"]).exists() -> Image.open(x["photo_path"])
теперь должны идти через resolve_local_photo_path(...) ниже — он одинаково
обрабатывает оба случая и не запрашивает сеть повторно на каждую
перерисовку списка (кэш на диске по хэшу URL)."""

import hashlib
from pathlib import Path

import requests

CACHE_DIR = Path("photo_cache")
CACHE_DIR.mkdir(exist_ok=True)

_TIMEOUT_SECONDS = 15


def resolve_local_photo_path(photo_path):
    """Возвращает pathlib.Path к файлу на диске, готовому для
    PIL.Image.open(...), либо None, если фото нет или недоступно."""
    if not photo_path:
        return None
    s = str(photo_path)
    if s.startswith("http://") or s.startswith("https://"):
        return _get_cached(s)
    p = Path(s)
    return p if p.exists() else None


def _get_cached(url: str):
    suffix = Path(url.split("?")[0]).suffix or ".jpg"
    cache_key = hashlib.sha1(url.encode("utf-8")).hexdigest()
    local_path = CACHE_DIR / f"{cache_key}{suffix}"
    if local_path.exists():
        return local_path
    try:
        resp = requests.get(url, timeout=_TIMEOUT_SECONDS)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[photo_cache] не удалось скачать {url}: {e}")
        return None
    local_path.write_bytes(resp.content)
    return local_path
