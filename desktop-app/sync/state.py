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
        # RLock, а не Lock: _check_id_map_integrity вызывается из _create_tables,
        # который уже держит этот же мьютекс — вложенный захват обязан сработать.
        self._lock = threading.RLock()
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

                -- Снимок данных турнира (name/date/location) на момент
                -- первой попытки синхронизации. Нужен, чтобы при 404
                -- "Соревнование не найдено" (например, после пересоздания
                -- центральной БД) можно было пересоздать соревнование на
                -- сервере заново, не заглядывая в armwrestling.db.
                CREATE TABLE IF NOT EXISTS competition_source (
                    local_id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    date TEXT NOT NULL,
                    location TEXT,
                    weight_tolerance REAL,
                    bracket_system TEXT,
                    format_type TEXT
                );

                -- "Курсор" обратной синхронизации (сайт -> десктоп): последний
                -- server_time, полученный от GET /sync/<entity>/changes, чтобы
                -- в следующий раз спросить только то, что изменилось С ЭТОГО
                -- момента, а не всю базу целиком. Ключ — имя набора изменений
                -- (пока только "athletes"), значение — ISO-таймстамп сервера.
                CREATE TABLE IF NOT EXISTS sync_cursors (
                    name TEXT PRIMARY KEY,
                    since_value TEXT NOT NULL
                );
                """
            )
            self.conn.commit()
            cs_cols = [r[1] for r in self.conn.execute("PRAGMA table_info(competition_source)").fetchall()]
            for col in ("weight_tolerance", "bracket_system", "format_type"):
                if col not in cs_cols:
                    ddl = "REAL" if col == "weight_tolerance" else "TEXT"
                    self.conn.execute(f"ALTER TABLE competition_source ADD COLUMN {col} {ddl}")
            self.conn.commit()
            self._check_id_map_integrity()

    # ── карта id ──────────────────────────────────────────────
    # Сущности, для которых привязка local -> remote строго один-к-одному.
    # (athlete_of_participant — наоборот, многие-к-одному: один спортсмен
    # может участвовать в нескольких турнирах, поэтому его тут НЕТ.)
    _ONE_TO_ONE = ("athlete", "coach", "club", "competition", "category", "participant", "match")

    def _check_id_map_integrity(self):
        """Находит привязки многие-к-одному (несколько локальных карточек
        указывают на один remote) для сущностей, где должно быть 1:1. Раньше
        такое молча накапливалось и ломало обратную синхронизацию: remote
        сопоставлялся с первой локальной карточкой, а остальные не получали
        обновлений (пример — три локальных спортсмена, «смотревшие» на одну
        скрытую на сайте карточку). Запускается при старте, только логирует."""
        with self._lock:
            rows = self.conn.execute(
                f"""
                SELECT entity_type, remote_id, COUNT(*) AS c
                FROM id_map
                WHERE entity_type IN ({",".join("?" * len(self._ONE_TO_ONE))})
                GROUP BY entity_type, remote_id
                HAVING COUNT(*) > 1
                """,
                self._ONE_TO_ONE,
            ).fetchall()
        for r in rows:
            print(f"[sync] WARNING id_map: {r['entity_type']} remote={r['remote_id']} "
                  f"bound to {r['c']} local rows — many-to-one; "
                  "this breaks reverse sync")

    def map_get(self, entity_type: str, local_id: int) -> int | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT remote_id FROM id_map WHERE entity_type=? AND local_id=?",
                (entity_type, local_id),
            ).fetchone()
            return row["remote_id"] if row else None

    def map_get_local(self, entity_type: str, remote_id: int) -> int | None:
        """Обратный поиск: по центральному id найти локальный. Нужен для
        обратной синхронизации (сайт -> десктоп, см. sync/pull_sync.py) —
        десктоп получает список изменённых записей с их central id и должен
        понять, это уже известная ему запись (обновить) или новая (создать)."""
        with self._lock:
            row = self.conn.execute(
                "SELECT local_id FROM id_map WHERE entity_type=? AND remote_id=?",
                (entity_type, remote_id),
            ).fetchone()
            return row["local_id"] if row else None

    def map_set(self, entity_type: str, local_id: int, remote_id: int) -> bool:
        """Записывает привязку local -> remote; True если записана.

        Для сущностей с жёстким 1:1 (спортсмен/тренер/клуб/турнир/категория/
        участник/матч) отказывается создавать многие-к-одному: если remote_id
        уже привязан к ДРУГОЙ локальной карточке, это сигнал о повреждении
        карты (несколько локальных карточек на одного центрального). Раньше
        такой маппинг молча записывался (INSERT OR REPLACE по primary key
        (entity_type, local_id) никак не мешал дублировать remote_id) и ломал
        обратную синхронизацию. Теперь: печатаем предупреждение и НЕ пишем.
        """
        with self._lock:
            if entity_type in self._ONE_TO_ONE:
                other = self.conn.execute(
                    "SELECT local_id FROM id_map WHERE entity_type=? AND remote_id=? AND local_id<>?",
                    (entity_type, remote_id, local_id),
                ).fetchone()
                if other is not None:
                    print(f"[sync] WARNING map_set {entity_type}: remote {remote_id} already bound to "
                          f"local {other['local_id']}, not binding to {local_id} "
                          "(guard against many-to-one)")
                    return False
            self.conn.execute(
                "INSERT OR REPLACE INTO id_map (entity_type, local_id, remote_id) VALUES (?,?,?)",
                (entity_type, local_id, remote_id),
            )
            self.conn.commit()
            return True

    def map_delete(self, entity_type: str, local_id: int) -> None:
        """Удаляет связку из id_map (например, если матч был удалён на сервере)."""
        with self._lock:
            self.conn.execute(
                "DELETE FROM id_map WHERE entity_type=? AND local_id=?",
                (entity_type, local_id),
            )
            self.conn.commit()

    # ── снимок данных турнира для самолечения ────────────────
    def save_competition_source(self, tid: int, name: str, date: str, location: str | None,
                                 weight_tolerance: float | None = None,
                                 bracket_system: str | None = None,
                                 format_type: str | None = None) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO competition_source "
                "(local_id, name, date, location, weight_tolerance, bracket_system, format_type) "
                "VALUES (?,?,?,?,?,?,?)",
                (tid, name, date, location, weight_tolerance, bracket_system, format_type),
            )
            self.conn.commit()

    def get_competition_source(self, tid: int) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(
                "SELECT * FROM competition_source WHERE local_id=?", (tid,)
            ).fetchone()

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

    def exists(self, queue_id: int) -> bool:
        """Проверяет, что строка очереди ещё не была удалена — нужно
        внутри flush_pending(), т.к. pending() забирает весь список ОДИН
        раз в начале прогонки, а самолечение (см.
        _self_heal_missing_tournament) может по ходу удалить из БД ещё не
        обработанные строки того же tid, которые уже сидят в этом старом
        списке в памяти."""
        with self._lock:
            row = self.conn.execute(
                "SELECT 1 FROM pending_queue WHERE id=?", (queue_id,)
            ).fetchone()
            return row is not None

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

    def purge_pending_by_operation(self, operation: str, filter_fn=None) -> int:
        """Удаляет из очереди операции по operation и опциональному фильтру.
        filter_fn(payload) -> bool: если True — удаляем."""
        with self._lock:
            rows = self.conn.execute(
                "SELECT id, payload FROM pending_queue WHERE operation=?", (operation,)
            ).fetchall()
            removed = 0
            for row in rows:
                payload = json.loads(row["payload"])
                if filter_fn is None or filter_fn(payload):
                    self.conn.execute("DELETE FROM pending_queue WHERE id=?", (row["id"],))
                    removed += 1
            if removed:
                self.conn.commit()
            return removed

    def pending_count(self) -> int:
        with self._lock:
            row = self.conn.execute("SELECT COUNT(*) as c FROM pending_queue").fetchone()
            return row["c"]

    def has_pending(self, operation: str, id_key: str, id_value) -> bool:
        """Есть ли уже в очереди операция данного типа с payload[id_key] == id_value.
        Используется reconcile: повторный вызов (повторное открытие турнира,
        второе нажатие «Обновить данные») не должен плодить дубли create_match
        для одних и тех же mid, пока первый ещё висит в очереди (нет сети)."""
        with self._lock:
            rows = self.conn.execute(
                "SELECT payload FROM pending_queue WHERE operation=?", (operation,)
            ).fetchall()
            for row in rows:
                if json.loads(row["payload"]).get(id_key) == id_value:
                    return True
            return False

    # ── курсор обратной синхронизации (сайт -> десктоп) ─────────
    def get_cursor(self, name: str) -> str | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT since_value FROM sync_cursors WHERE name=?", (name,)
            ).fetchone()
            return row["since_value"] if row else None

    def set_cursor(self, name: str, since_value: str) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO sync_cursors (name, since_value) VALUES (?,?)",
                (name, since_value),
            )
            self.conn.commit()

    def close(self):
        with self._lock:
            self.conn.close()
