"""Автоматические backup соревнования + аварийный экспорт.

Правила:
- backup запрашивается после критических операций (завершённый матч,
  создание сетки, завершение турнира) и «тикером» каждые ~10 секунд;
- фактическая запись выполняется не чаще раза в `min_interval` секунд
  (по умолчанию 45) — файл маленький, но лишний IO не нужен;
- хранится не более `keep` последних файлов (по умолчанию 10);
- имя: <название>_<ГГГГ_ММ_ДД_ЧЧ-ММ>.armwrestling в папке backups/ рядом с БД;
- аварийный экспорт — немедленная запись с меткой _emergency_;
- check_integrity() — PRAGMA quick_check локальной БД перед экспортом.
"""

import glob
import os
import re
import time
from datetime import datetime

from .exporter import export_competition, ExportError

# Скользящее окно бэкапов (файлов в папке, включая emergency).
DEFAULT_KEEP = 10
DEFAULT_MIN_INTERVAL_SECONDS = 45


def _sanitize(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "_", str(name)).strip()
    return (name or "competition")[:60]


def _ts_now():
    return datetime.now().strftime("%Y_%m_%d_%H-%M-%S")


class BackupManager:
    def __init__(self, conn=None, state=None, backup_dir: str | None = None,
                 keep: int = DEFAULT_KEEP,
                 min_interval: float = DEFAULT_MIN_INTERVAL_SECONDS):
        self.conn = conn
        self.state = state
        self.backup_dir = backup_dir
        self.keep = keep
        self.min_interval = min_interval
        self._requested = False
        self._last_backup_at = 0.0
        self._last_backup_path = None
        self._emergency_last_path = None
        self._lock = __import__("threading").RLock()

    def configure(self, conn=None, state=None, backup_dir: str | None = None):
        """Вызывается при старте приложения (до первого использования)."""
        self.conn = conn
        self.state = state
        if backup_dir:
            self.backup_dir = backup_dir
        if self.backup_dir:
            os.makedirs(self.backup_dir, exist_ok=True)

    # ── статус ────────────────────────────────────────────────────
    def latest_backup(self) -> dict | None:
        """Информация о самом свежем backup-файле: {path, time, age}."""
        if not self.backup_dir or not os.path.isdir(self.backup_dir):
            return None
        files = glob.glob(os.path.join(self.backup_dir, "*.armwrestling"))
        if not files:
            return None
        newest = max(files, key=os.path.getmtime)
        mtime = os.path.getmtime(newest)
        return {"path": newest, "time": mtime,
                "age": max(0, time.time() - mtime)}

    def check_integrity(self) -> tuple:
        """(ok, message) — PRAGMA quick_check локальной БД."""
        if self.conn is None:
            return True, ""
        try:
            row = self.conn.execute("PRAGMA quick_check").fetchone()
            ok = row and row[0] == "ok"
            return ok, ("" if ok else f"Локальная БД повреждена: {row[0]}")
        except Exception as e:
            return False, f"Не удалось проверить локальную БД: {e}"

    # ── авто-бэкап ────────────────────────────────────────────────
    def request_backup(self):
        """Отмечает, что нужен бэкап (выполнится при ближайшем тике)."""
        with self._lock:
            self._requested = True

    def maybe_autobackup(self, tid: int | None, force: bool = False) -> bool:
        """Выполняет отложенный бэкап, если он запрошен и прошёл
        минимальный интервал. Возвращает True, если файл создан."""
        with self._lock:
            requested = self._requested
            self._requested = False
        if not requested and not force:
            return False
        if not force and (time.time() - self._last_backup_at
                          < self.min_interval):
            return False
        if tid is None:
            return False
        try:
            self._write_backup(tid, emergency=False)
            return True
        except Exception as e:
            print(f"[backup] ошибка авто-бэкапа: {e}")
            return False

    def autobackup_now(self, tid: int) -> str:
        """Немедленный бэкап (например, после завершения турнира)."""
        return self._write_backup(tid, emergency=False)

    def emergency_export(self, tid: int) -> str:
        """Аварийный экспорт: максимально быстро, без проверки
        целостности, имя с меткой _emergency_ и временем до минут."""
        return self._write_backup(tid, emergency=True)

    def _write_backup(self, tid: int, emergency: bool) -> str:
        if self.conn is None:
            raise ExportError("БД не инициализирована.")
        if not self.backup_dir:
            raise ExportError("Папка backup не настроена.")
        os.makedirs(self.backup_dir, exist_ok=True)
        name = "competition"
        try:
            row = self.conn.execute(
                "SELECT name FROM tournaments WHERE id=?", (tid,)).fetchone()
            if row:
                name = _sanitize(row["name"])
        except Exception:
            pass
        tag = "emergency" if emergency else "auto"
        dest = os.path.join(
            self.backup_dir, f"{name}_{tag}_{_ts_now()}.armwrestling")
        # Аварийный экспорт пропускает проверку целостности.
        export_competition(self.conn, self.state, tid, dest,
                           emergency=emergency)
        with self._lock:
            self._last_backup_at = time.time()
            self._last_backup_path = dest
            if emergency:
                self._emergency_last_path = dest
        self.rotate()
        return dest

    # ── ротация ───────────────────────────────────────────────────
    def rotate(self):
        """Удаляет старые файлы, оставляя `keep` последних по mtime."""
        if not self.backup_dir or not os.path.isdir(self.backup_dir):
            return
        files = glob.glob(os.path.join(self.backup_dir, "*.armwrestling"))
        if len(files) <= self.keep:
            return
        files.sort(key=os.path.getmtime)
        for old in files[:-self.keep]:
            try:
                os.remove(old)
            except OSError:
                pass

    def backup_count(self) -> int:
        if not self.backup_dir or not os.path.isdir(self.backup_dir):
            return 0
        return len(glob.glob(os.path.join(self.backup_dir, "*.armwrestling")))
