"""
Одноразовый скрипт: чинит уже стоящие в очереди записи create_category,
где max_weight == "Absolute" (строка), заменяя на null (число не нужно —
сервер и так трактует пустой max_weight как категорию без ограничения веса).

Запускать из папки desktop-app (рядом с armwrestling_tournament.py и
sync_state.db), например:

    python fix_sync_queue.py

Ничего не удаляет — только правит payload на месте, чтобы очередь
перестала спотыкаться об эти записи при следующей синхронизации.
"""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "sync_state.db"

if not DB_PATH.exists():
    raise SystemExit(f"Не найден {DB_PATH} — запусти скрипт из папки desktop-app")

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

rows = conn.execute(
    "SELECT id, payload FROM pending_queue WHERE operation='create_category'"
).fetchall()

fixed = 0
for row in rows:
    payload = json.loads(row["payload"])
    max_weight = payload.get("max_weight")
    if isinstance(max_weight, str):
        if max_weight.strip().lower() == "absolute":
            payload["max_weight"] = None
        else:
            # на случай "70+" и подобных — тоже приводим к числу
            try:
                payload["max_weight"] = float(max_weight.rstrip("+"))
            except ValueError:
                print(f"  ! не смог привести к числу: {max_weight!r} (id={row['id']}), пропускаю")
                continue
        conn.execute(
            "UPDATE pending_queue SET payload=? WHERE id=?",
            (json.dumps(payload, ensure_ascii=False), row["id"]),
        )
        fixed += 1
        print(f"  исправлено id={row['id']}: max_weight -> {payload['max_weight']!r}")

conn.commit()
conn.close()

print(f"\nГотово. Исправлено записей: {fixed} из {len(rows)} create_category в очереди.")
print("Теперь можно перезапускать приложение и нажимать «Синхронизировать» заново.")
