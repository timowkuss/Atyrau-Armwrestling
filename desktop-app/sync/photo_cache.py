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
import threading
from pathlib import Path

import requests

CACHE_DIR = Path("photo_cache")
CACHE_DIR.mkdir(exist_ok=True)

_TIMEOUT_SECONDS = 15

_download_lock = threading.Lock()
_inflight: set[str] = set()
_inflight_lock = threading.Lock()


def resolve_local_photo_path(photo_path, only_cached=False):
    """Возвращает pathlib.Path к файлу на диске, готовому для
    PIL.Image.open(...), либо None, если фото нет или недоступно.

    Если only_cached=True, облачные фото не скачиваются — возвращается
    None, если файл ещё не в локальном кэше.
    """
    if not photo_path:
        return None
    s = str(photo_path)
    if s.startswith("http://") or s.startswith("https://"):
        return _get_cached(s, only_cached=only_cached)
    p = Path(s)
    return p if p.exists() else None


def _get_cached(url: str, only_cached=False):
    suffix = Path(url.split("?")[0]).suffix or ".jpg"
    cache_key = hashlib.sha1(url.encode("utf-8")).hexdigest()
    local_path = CACHE_DIR / f"{cache_key}{suffix}"
    if local_path.exists():
        return local_path
    if only_cached:
        return None
    try:
        with _download_lock:
            if local_path.exists():
                return local_path
            resp = requests.get(url, timeout=_TIMEOUT_SECONDS)
            resp.raise_for_status()
            local_path.write_bytes(resp.content)
    except requests.RequestException as e:
        print(f"[photo_cache] не удалось скачать {url}: {e}")
        return None
    return local_path


def precache_photos(photo_paths, on_done=None):
    """Фоново скачивает облачные фото в локальный кэш.

    Все вызовы сюда должны быть НЕ-блокирующими: функция возвращается
    сразу, а скачивание идёт в daemon-потоке. on_done (если задан)
    вызывается в этом рабочем потоке ПОСЛЕ завершения скачивания —
    зовущий обычно делает self.after(0, ...) чтобы вернуться в UI-поток.

    Если скачивать нечего (все фото уже в кэше или пустой список),
    поток не создаётся и on_done не вызывается — это позволяет
    безопасно переиспользовать один и тот же колбэк на каждый рендер
    без бесконечного цикла перерисовок.
    """
    urls = [str(p) for p in (photo_paths or [])
            if p and str(p).startswith("http")]
    if not urls:
        return
    to_download = []
    for u in urls:
        suffix = Path(u.split("?")[0]).suffix or ".jpg"
        cache_key = hashlib.sha1(u.encode("utf-8")).hexdigest()
        if not (CACHE_DIR / f"{cache_key}{suffix}").exists():
            to_download.append(u)
    if not to_download:
        return
    with _inflight_lock:
        fresh = [u for u in to_download if u not in _inflight]
        if not fresh:
            return
        _inflight.update(fresh)

    def work():
        try:
            for u in fresh:
                try:
                    resolve_local_photo_path(u)
                except Exception:
                    pass
            if on_done:
                on_done()
        finally:
            with _inflight_lock:
                _inflight.difference_update(fresh)

    threading.Thread(target=work, daemon=True, name="photo-precache").start()
