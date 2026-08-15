"""Очистка sync_state.db (очередь и маппинги синхронизации).

Удаляет: id_map, sync_cursors, competition_source, pending_queue.
Предназначен для запуска ПОСЛЕ очистки основных БД (local + прод),
чтобы старые маппинги локальных/серверных id не вызывали конфликтов
при следующей синхронизации.

Перед очисткой делает копию файла рядом (sync_state.db.bak_*).
"""
import shutil
import sqlite3
import sys
import time

DB = r"sync_state.db"

TABLES = ["id_map", "sync_cursors", "competition_source", "pending_queue"]


def main() -> int:
    shutil.copy2(DB, f"{DB}.bak_{int(time.time())}")
    conn = sqlite3.connect(DB)
    try:
        conn.execute("BEGIN")

        def count(t):
            return conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]

        before = {t: count(t) for t in TABLES}
        for t in TABLES:
            conn.execute(f'DELETE FROM "{t}"')
            print(f"  DELETED {before[t]:6d} rows from {t}")

        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('id_map','pending_queue')")

        conn.commit()
        print("\nCOMMITTED.")
        return 0
    except Exception as e:
        conn.rollback()
        print("ROLLBACK:", e)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
