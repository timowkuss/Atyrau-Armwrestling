"""
Диагностика офлайн-очереди sync_manager.

Сверяет payload каждой операции в pending_queue (sync/state.db или как у тебя
называется файл — см. config.SYNC_STATE_DB_PATH) с текущим состоянием
armwrestling.db. Если сущность (турнир/категория/участник/матч), на которую
ссылается операция в очереди, в основной базе уже НЕ существует — значит,
это "мёртвая" запись: она была создана/обновлена офлайн, а потом удалена
локально, но из очереди не убрана.

Запуск:
    python check_stale_queue.py

Пути к базам подставь свои (или замени на импорт config, если скрипт лежит
рядом с проектом):
    from sync import config
    SYNC_DB = config.SYNC_STATE_DB_PATH
"""

import json
import sqlite3
from pathlib import Path

# ── поправь пути под себя ──
MAIN_DB = "C:/Users/kusaj/Desktop/desktop-app/armwrestling.db"
SYNC_DB = "C:/Users/kusaj/Desktop/desktop-app/sync_state.db"


def table_has_id(conn, table, id_col, value):
    row = conn.execute(f"SELECT 1 FROM {table} WHERE {id_col}=?", (value,)).fetchone()
    return row is not None


def main():
    if not Path(MAIN_DB).exists() or not Path(SYNC_DB).exists():
        print(f"Не найден один из файлов: {MAIN_DB}, {SYNC_DB}\n"
              f"Поправь пути MAIN_DB / SYNC_DB в начале скрипта.")
        return

    main_conn = sqlite3.connect(MAIN_DB)
    main_conn.row_factory = sqlite3.Row
    sync_conn = sqlite3.connect(SYNC_DB)
    sync_conn.row_factory = sqlite3.Row

    rows = sync_conn.execute("SELECT * FROM pending_queue ORDER BY id").fetchall()
    print(f"Всего операций в очереди: {len(rows)}\n")

    stale = []
    alive = []

    checks = {
        "create_competition": ("tournaments", "id", "tid"),
        "create_category": ("weight_categories", "id", "cid"),
        "create_participant": ("participants", "id", "pid"),
        "create_match": ("matches", "id", "mid"),
        "update_match": ("matches", "id", "mid"),
        "create_athlete": ("athletes", "id", "aid"),
        "update_athlete": ("athletes", "id", "aid"),
    }

    for row in rows:
        op = row["operation"]
        payload = json.loads(row["payload"])
        check = checks.get(op)

        if not check:
            alive.append(row)
            continue

        table, id_col, payload_key = check
        local_id = payload.get(payload_key)
        exists = local_id is not None and table_has_id(main_conn, table, id_col, local_id)

        if exists:
            alive.append(row)
        else:
            stale.append((row, table, local_id))

    print(f"— Похожи на актуальные: {len(alive)}")
    print(f"— МЁРТВЫЕ (ссылаются на уже удалённые/несуществующие записи): {len(stale)}\n")

    if stale:
        print("Подробности по мёртвым записям:")
        for row, table, local_id in stale:
            print(f"  очередь id={row['id']:>4}  op={row['operation']:<20} "
                  f"-> {table}.id={local_id} (не найден в {MAIN_DB})")
        print("\nЭти записи безопасно удалить из pending_queue вручную, например:")
        print("  DELETE FROM pending_queue WHERE id IN (" +
              ", ".join(str(r["id"]) for r, _, _ in stale) + ");")

    main_conn.close()
    sync_conn.close()


if __name__ == "__main__":
    main()
