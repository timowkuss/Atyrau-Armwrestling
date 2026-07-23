"""
Полная диагностика офлайн-очереди синхронизации. Ничего не меняет,
только читает sync_state.db и armwrestling.db.

Положи рядом с armwrestling_tournament.py (в папку desktop-app/) и
запусти:

    python list_full_queue.py

Печатает ВСЕ строки pending_queue по порядку (в котором их будет
обрабатывать flush_pending), и для update_match/create_match — есть ли
локально сам матч, есть ли remote_id (замаплен ли), и есть ли
last_error/сколько было попыток. Так будет видно, на какой именно
строке очередь реально останавливается (не проходит из-за настоящей
ошибки), а не просто "ждёт" (это не блокирует, просто пропускается).
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
        "SELECT id, operation, payload, created_at, attempts, last_error "
        "FROM pending_queue ORDER BY id"
    ).fetchall()

    print(f"Всего строк в очереди: {len(rows)}\n")

    for r in rows:
        payload = json.loads(r["payload"])
        op = r["operation"]
        attempts = r["attempts"]
        last_error = r["last_error"]

        line = f"id={r['id']:4d} op={op:16s} attempts={attempts} "

        if op in ("create_match", "update_match"):
            mid = payload.get("mid")
            local_row = aconn.execute(
                "SELECT id, status, category_id FROM matches WHERE id=?", (mid,)
            ).fetchone()
            exists_locally = local_row is not None

            mapped = sconn.execute(
                "SELECT remote_id FROM id_map WHERE entity_type='match' AND local_id=?",
                (mid,),
            ).fetchone()
            remote_id = mapped["remote_id"] if mapped else None

            cat_id = payload.get("category_id") or (local_row["category_id"] if local_row else None)
            cat_mapped = None
            if cat_id is not None:
                catrow = sconn.execute(
                    "SELECT remote_id FROM id_map WHERE entity_type='category' AND local_id=?",
                    (cat_id,),
                ).fetchone()
                cat_mapped = catrow["remote_id"] if catrow else None

            line += (
                f"mid={mid} локально_есть={exists_locally} "
                f"remote_id={remote_id} category_id={cat_id} category_remote={cat_mapped}"
            )
        else:
            line += f"payload={payload}"

        if last_error:
            line += f"\n         !!! last_error={last_error}"

        print(line)

    sconn.close()
    aconn.close()


if __name__ == "__main__":
    main()
