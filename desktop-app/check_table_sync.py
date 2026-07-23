"""
Показывает все матчи заданной категории/руки: локальный table_number,
статус, замаплен ли на сервер (remote_id), и есть ли для него в
офлайн-очереди незавершённая операция (значит, обновление ещё не
долетело до сервера).

Положи рядом с armwrestling_tournament.py (в папку desktop-app/) и
запусти, подставив свою категорию и руку:

    python check_table_sync.py "80kg" "Правая"

(первый аргумент — часть названия категории, второй — "Правая" или
"Левая"; регистр не важен)
"""
import json
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SYNC_DB = BASE / "sync_state.db"
APP_DB = BASE / "armwrestling.db"


def main():
    if len(sys.argv) < 3:
        print('Использование: python check_table_sync.py "часть_названия_категории" "Правая|Левая"')
        return

    cat_substr = sys.argv[1]
    hand = sys.argv[2]

    if not SYNC_DB.exists() or not APP_DB.exists():
        print("Не найдены sync_state.db / armwrestling.db — запусти из папки desktop-app")
        return

    sconn = sqlite3.connect(str(SYNC_DB))
    sconn.row_factory = sqlite3.Row
    aconn = sqlite3.connect(str(APP_DB))
    aconn.row_factory = sqlite3.Row

    cats = aconn.execute(
        "SELECT id, name FROM weight_categories WHERE name LIKE ?", (f"%{cat_substr}%",)
    ).fetchall()
    if not cats:
        print(f"Категория с '{cat_substr}' в названии не найдена.")
        return

    for cat in cats:
        matches = aconn.execute(
            "SELECT id, round_name, bracket, stage, status, p1_id, p2_id, table_number "
            "FROM matches WHERE category_id=? AND hand=? ORDER BY stage, match_order",
            (cat["id"], hand),
        ).fetchall()
        if not matches:
            continue

        print(f"\n=== Категория: {cat['name']} (id={cat['id']}), рука={hand} ===")
        for m in matches:
            mid = m["id"]
            mapped = sconn.execute(
                "SELECT remote_id FROM id_map WHERE entity_type='match' AND local_id=?",
                (mid,),
            ).fetchone()
            remote_id = mapped["remote_id"] if mapped else None

            pending_rows = sconn.execute(
                "SELECT id, operation, payload FROM pending_queue"
            ).fetchall()
            pending_for_this = []
            for pr in pending_rows:
                payload = json.loads(pr["payload"])
                if payload.get("mid") == mid:
                    pending_for_this.append((pr["id"], pr["operation"], payload))

            print(
                f"  mid={mid:5d} stage={m['stage']} {m['round_name']:24s} "
                f"status={m['status']:8s} p1={m['p1_id']} p2={m['p2_id']} "
                f"table_number_local={m['table_number']} remote_id={remote_id}"
            )
            for queue_id, op, payload in pending_for_this:
                print(f"        !!! В ОЧЕРЕДИ: queue_row_id={queue_id} op={op} payload={payload}")

    sconn.close()
    aconn.close()


if __name__ == "__main__":
    main()
