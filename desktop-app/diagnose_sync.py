"""Диагностика зависшей синхронизации. Положи этот файл рядом с
armwrestling_tournament.py (в папку desktop-app/) и запусти:

    python diagnose_sync.py

Ничего не меняет, только читает sync_state.db и armwrestling.db и
печатает, что происходит с очередью и картой id.
"""
import json
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent
SYNC_DB = BASE / "sync_state.db"
APP_DB = BASE / "armwrestling.db"

STUCK_MIDS = [382, 383, 384, 385, 386]  # <-- поменяй на свои id при желании


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

    print("=" * 70)
    print("1) Очередь pending_queue — сколько операций и каких")
    print("=" * 70)
    rows = sconn.execute(
        "SELECT operation, COUNT(*) as c FROM pending_queue GROUP BY operation"
    ).fetchall()
    if not rows:
        print("  очередь ПУСТА")
    for r in rows:
        print(f"  {r['operation']:20s} {r['c']}")

    print()
    print("=" * 70)
    print("2) create_match/update_match в очереди для интересующих mid")
    print("=" * 70)
    rows = sconn.execute(
        "SELECT id, operation, payload, created_at FROM pending_queue "
        "WHERE operation IN ('create_match','update_match') ORDER BY id"
    ).fetchall()
    found_any = False
    for r in rows:
        payload = json.loads(r["payload"])
        if payload.get("mid") in STUCK_MIDS:
            found_any = True
            print(f"  queue_row_id={r['id']} op={r['operation']} created_at={r['created_at']} payload={payload}")
    if not found_any:
        print("  НИЧЕГО не найдено для этих mid — значит create_match для них "
              "никогда не попадал в очередь (или уже был оттуда удалён).")

    print()
    print("=" * 70)
    print("3) id_map (match) для интересующих mid — есть ли remote_id")
    print("=" * 70)
    for mid in STUCK_MIDS:
        row = sconn.execute(
            "SELECT * FROM id_map WHERE entity_type='match' AND local_id=?", (mid,)
        ).fetchone()
        if row:
            print(f"  mid={mid} -> remote_id={row['remote_id']} (замаплен)")
        else:
            print(f"  mid={mid} -> НЕ замаплен (remote_id неизвестен)")

    print()
    print("=" * 70)
    print("4) Сами матчи в локальной armwrestling.db — откуда они и когда")
    print("=" * 70)
    for mid in STUCK_MIDS:
        row = aconn.execute("SELECT * FROM matches WHERE id=?", (mid,)).fetchone()
        if row:
            d = dict(row)
            print(f"  mid={mid}: category_id={d.get('category_id')} hand={d.get('hand')} "
                  f"tournament_id={d.get('tournament_id')} round={d.get('round_name')} "
                  f"bracket={d.get('bracket')} status={d.get('status')}")
        else:
            print(f"  mid={mid}: СТРОКИ НЕТ в локальной таблице matches (уже удалён локально?)")

    print()
    print("=" * 70)
    print("5) Схема pending_queue (на случай, если названия колонок другие)")
    print("=" * 70)
    cols = sconn.execute("PRAGMA table_info(pending_queue)").fetchall()
    print("  колонки:", [c["name"] for c in cols])

    print()
    print("=" * 70)
    print("6) Категория этих матчей — есть ли она в id_map (category)")
    print("=" * 70)
    cat_ids = set()
    for mid in STUCK_MIDS:
        row = aconn.execute("SELECT category_id FROM matches WHERE id=?", (mid,)).fetchone()
        if row:
            cat_ids.add(row["category_id"])
    for cid in cat_ids:
        row = sconn.execute(
            "SELECT * FROM id_map WHERE entity_type='category' AND local_id=?", (cid,)
        ).fetchone()
        if row:
            print(f"  category_id={cid} -> remote_id={row['remote_id']}")
        else:
            print(f"  category_id={cid} -> НЕ замаплена на сервере! (вот это, скорее всего, и есть причина)")

    sconn.close()
    aconn.close()


if __name__ == "__main__":
    main()
