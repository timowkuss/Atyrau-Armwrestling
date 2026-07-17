"""Настройки синхронизации с центральной базой. Значения можно
переопределить переменными окружения или файлом sync_config.json рядом с
armwrestling_tournament.py (удобно для организатора без консоли)."""

import json
import os
from pathlib import Path

_CONFIG_FILE = Path(__file__).resolve().parent.parent / "sync_config.json"

_defaults = {
    "API_BASE_URL": "http://localhost:8000/api/v1/sync",
    "DESKTOP_SYNC_TOKEN": "change-me-desktop-sync-token",
    "SYNC_ENABLED": True,
    "REQUEST_TIMEOUT_SECONDS": 5,
}


def _load():
    cfg = dict(_defaults)
    if _CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(_CONFIG_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    for key in cfg:
        env_val = os.environ.get(key)
        if env_val is not None:
            cfg[key] = env_val
    return cfg


_cfg = _load()

API_BASE_URL: str = _cfg["API_BASE_URL"]
DESKTOP_SYNC_TOKEN: str = _cfg["DESKTOP_SYNC_TOKEN"]
SYNC_ENABLED: bool = bool(_cfg["SYNC_ENABLED"]) and str(_cfg["SYNC_ENABLED"]).lower() not in (
    "0",
    "false",
)
REQUEST_TIMEOUT_SECONDS: float = float(_cfg["REQUEST_TIMEOUT_SECONDS"])

# Отдельный файл для карты локальных <-> центральных id и офлайн-очереди —
# намеренно НЕ armwrestling.db, чтобы не трогать существующую схему.
SYNC_STATE_DB_PATH = Path(__file__).resolve().parent.parent / "sync_state.db"
