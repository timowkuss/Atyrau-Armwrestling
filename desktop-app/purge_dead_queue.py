"""
Чистит офлайн-очередь синхронизации от "мёртвых" записей create_match/
update_match — тех, что ссылаются на match id (mid), которого больше
нет в локальной armwrestling.db (матч был удалён локально, например
при пересоздании сетки). Такие записи никогда не выполнятся и просто
бесполезно перемалываются на каждой синхронизации.

Ничего другого не трогает: если mid существует локально — строка
остаётся в очереди как есть, даже если ещё не замаплена на сервер.

Положи рядом с armwrestling_tournament.py (в папку desktop-app/) и
запусти:

    python purge_dead_queue.py

Сначала покажет, что будет удалено (dry-run), и попросит подтверждение.
"""
import json
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent
SYNC_DB = BASE / "sync_state.db"
APP_DB = BASE / "armwrestling.db"


def main():
    if not SYNC_DB.exists():
        print(f"НЕТ ФАЙЛА: {SYNC_DB}")
        return
    if not APP_DB.exists():
        print(f"НЕТ ФАЙЛА: {APP_DB}")
        return

    sconn = sqlite3.connect(str(SYNC_DB))
    sconn.row_factory = sqlite3.Row
    aconn = sqlite3.connect(str(APP_DB))
    aconn.row_factory = sqlite3.Row

    rows = sconn.execute(
        "SELECT id, operation, payload FROM pending_queue "
        "WHERE operation IN ('create_match','update_match') ORDER BY id"
    ).fetchall()

    to_delete = []
    for r in rows:
        payload = json.loads(r["payload"])
        mid = payload.get("mid")
        if mid is None:
            continue
        exists_locally = aconn.execute(
            "SELECT 1 FROM matches WHERE id=?", (mid,)
        ).fetchone() is not None
        if not exists_locally:
            to_delete.append((r["id"], r["operation"], mid))

    if not to_delete:
        print("Мёртвых записей не найдено — очередь чистая.")
        sconn.close()
        aconn.close()
        return

    print(f"Найдено {len(to_delete)} мёртвых записей (матч удалён локально):")
    for queue_id, op, mid in to_delete:
        print(f"  queue_row_id={queue_id} op={op} mid={mid}")

    answer = input(f"\nУдалить эти {len(to_delete)} записей из очереди? (yes/no): ").strip().lower()
    if answer != "yes":
        print("Отменено, ничего не удалено.")
        sconn.close()
        aconn.close()
        return

    ids = [row[0] for row in to_delete]
    sconn.executemany("DELETE FROM pending_queue WHERE id=?", [(i,) for i in ids])
    sconn.commit()

    print(f"\nГотово. Удалено {len(ids)} записей из очереди.")
    sconn.close()
    aconn.close()


if __name__ == "__main__":
    main()
