"""Отдельная лёгкая SQLite-база (НЕ armwrestling.db) для двух вещей:

1. Карта локальных id <-> центральных id (спортсмен/турнир/категория/
   участник/матч), чтобы при следующей синхронизации знать, что уже
   отправлено и с каким id в центральной базе.
2. Офлайн-очередь: если запрос к API не удался (нет сети), операция
   сохраняется здесь и будет повторена при следующем вызове flush_pending()
   (например, при следующем запуске программы или по кнопке
   "Повторить синхронизацию").

Отдельный файл — намеренно, чтобы ни при каких обстоятельствах не
затрагивать существующую схему armwrestling.db.
"""

import json
import sqlite3
import threading
import time

from . import config


class SyncState:
    def __init__(self, db_path=None):
        # check_same_thread=False: эта БД теперь используется и из главного
        # потока (ручная кнопка "Синхронизировать"), и из фонового потока,
        # которым генерация сетки отправляет офлайн-очередь на сервер (см.
        # _run_batched_bracket_generation в armwrestling_tournament.py).
        # Сам sqlite3.Connection не потокобезопасен для одновременных
        # вызовов, поэтому все операции ниже дополнительно защищены
        # self._lock — это делает НЕ параллельными, а последовательными
        # обращения из разных потоков, что достаточно для локальной очереди
        # и не блокирует UI (запись в SQLite — доли миллисекунды).
        self.conn = sqlite3.connect(
            str(db_path or config.SYNC_STATE_DB_PATH), check_same_thread=False
        )
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._create_tables()

    def _create_tables(self):
        with self._lock:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS id_map (
                    entity_type TEXT NOT NULL,
                    local_id INTEGER NOT NULL,
                    remote_id INTEGER NOT NULL,
                    PRIMARY KEY (entity_type, local_id)
                );

                CREATE TABLE IF NOT EXISTS pending_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT
                );
                """
            )
            self.conn.commit()

    # ── карта id ──────────────────────────────────────────────
    def map_get(self, entity_type: str, local_id: int) -> int | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT remote_id FROM id_map WHERE entity_type=? AND local_id=?",
                (entity_type, local_id),
            ).fetchone()
            return row["remote_id"] if row else None

    def map_set(self, entity_type: str, local_id: int, remote_id: int) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO id_map (entity_type, local_id, remote_id) VALUES (?,?,?)",
                (entity_type, local_id, remote_id),
            )
            self.conn.commit()

    # ── офлайн-очередь ───────────────────────────────────────
    def enqueue(self, operation: str, payload: dict) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO pending_queue (operation, payload, created_at) VALUES (?,?,?)",
                (operation, json.dumps(payload, ensure_ascii=False), time.time()),
            )
            self.conn.commit()

    def pending(self) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(
                "SELECT * FROM pending_queue ORDER BY id"
            ).fetchall()

    def mark_done(self, queue_id: int) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM pending_queue WHERE id=?", (queue_id,))
            self.conn.commit()

    def mark_failed(self, queue_id: int, error: str) -> None:
        with self._lock:
            self.conn.execute(
                "UPDATE pending_queue SET attempts = attempts + 1, last_error=? WHERE id=?",
                (error, queue_id),
            )
            self.conn.commit()

    def purge_pending(self, operation: str, id_key: str, id_value) -> int:
        """Удаляет из очереди ещё не отправленные операции с данным именем,
        у которых payload[id_key] == id_value. Нужно вызывать при локальном
        удалении сущности, чтобы она не «воскресла» на сервере при flush_pending()."""
        with self._lock:
            rows = self.conn.execute(
                "SELECT id, payload FROM pending_queue WHERE operation=?", (operation,)
            ).fetchall()
            removed = 0
            for row in rows:
                payload = json.loads(row["payload"])
                if payload.get(id_key) == id_value:
                    self.conn.execute("DELETE FROM pending_queue WHERE id=?", (row["id"],))
                    removed += 1
            if removed:
                self.conn.commit()
            return removed

    def pending_count(self) -> int:
        with self._lock:
            row = self.conn.execute("SELECT COUNT(*) as c FROM pending_queue").fetchone()
            return row["c"]

    def close(self):
        with self._lock:
            self.conn.close()
