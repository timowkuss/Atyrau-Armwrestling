"""Централизованное определение путей к файлам и папкам приложения.

Работает одинаково в двух режимах:

- dev (``python armwrestling_tournament.py``): данные лежат рядом с кодом
  (папка desktop-app/) — ровно как было до упаковки;
- frozen (PyInstaller-сборка ``AtyrauArmwrestling.exe``): пользовательские
  данные уходят в ``%APPDATA%\\AtyrauArmwrestling`` (writable-папка, не
  Program Files), ресурсы читаются из ``sys._MEIPASS`` (внутри exe).

Никаких абсолютных путей вида ``C:\\Users\\...`` — всё строится от
``__file__``/``sys.executable``/``APPDATA``, поэтому приложение переносимо
между компьютерами независимо от имени пользователя.
"""

import os
import sys
from pathlib import Path

APP_DIR_NAME = "AtyrauArmwrestling"


def is_frozen() -> bool:
    """True, если код выполняется из PyInstaller-сборки."""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Корневая папка данных приложения (writable).

    - dev: папка рядом с кодом (desktop-app/);
    - frozen: ``%APPDATA%\\AtyrauArmwrestling``.
    """
    if is_frozen():
        base = os.environ.get("APPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_DIR_NAME
    return Path(__file__).resolve().parent


def resource_dir() -> Path:
    """Папка с ресурсами (assets/).

    - dev: папка рядом с кодом (desktop-app/);
    - frozen: sys._MEIPASS (внутри exe, read-only).
    """
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(rel: str) -> Path:
    """Путь к ресурсу относительно корня приложения (например
    ``assets/logo-atyrau-city.png``)."""
    return resource_dir() / rel


def data_path(*parts: str) -> Path:
    """Путь к файлу/папке данных в writable-каталоге приложения."""
    return app_dir().joinpath(*parts)


# ── конкретные файлы/папки приложения ────────────────────────────
def db_path() -> Path:
    return data_path("armwrestling.db")


def sync_state_db_path() -> Path:
    return data_path("sync_state.db")


def photos_dir() -> Path:
    return data_path("photos")


def photo_cache_dir() -> Path:
    return data_path("photo_cache")


def backups_dir() -> Path:
    return data_path("backups")


def config_file() -> Path:
    """Файл sync_config.json: writable-копия в AppData (если есть), иначе
    рядом с exe, иначе упакованный внутри exe (sys._MEIPASS, чтение),
    иначе рядом с кодом (dev)."""
    if is_frozen():
        appdata = data_path("sync_config.json")
        if appdata.exists():
            return appdata
        exe_dir = Path(sys.executable).resolve().parent / "sync_config.json"
        if exe_dir.exists():
            return exe_dir
        bundled = resource_path("sync_config.json")
        if bundled.exists():
            return bundled
        return appdata
    return Path(__file__).resolve().parent / "sync_config.json"


def env_file() -> Path:
    """Файл .env для переопределения переменных окружения."""
    if is_frozen():
        appdata = data_path(".env")
        if appdata.exists():
            return appdata
        exe_dir = Path(sys.executable).resolve().parent / ".env"
        if exe_dir.exists():
            return exe_dir
        return appdata
    return Path(__file__).resolve().parent / ".env"
