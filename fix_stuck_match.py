"""
Разовый скрипт: убирает застрявшую операцию update_match для mid=195
(матч удалён на сервере, но связка в id_map осталась), которая блокировала
весь flush_pending().

Запуск (из папки Armwrestling, там же где лежит desktop-app/):
    python fix_stuck_match.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("desktop-app/sync_state.db")
MID = 195

if not DB_PATH.exists():
    raise SystemExit(f"Не найден {DB_PATH.resolve()} — запусти скрипт из папки Armwrestling")

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

# 1. убираем застрявшую операцию из очереди
rows = conn.execute(
    "SELECT id, payload FROM pending_queue WHERE operation='update_match'"
).fetchall()
removed = 0
for row in rows:
    if f'"mid": {MID}' in row["payload"]:
        conn.execute("DELETE FROM pending_queue WHERE id=?", (row["id"],))
        removed += 1

# 2. чистим протухшую связку match -> remote_id
conn.execute("DELETE FROM id_map WHERE entity_type='match' AND local_id=?", (MID,))

conn.commit()
print(f"Удалено операций из очереди: {removed}")
print("Связка id_map для match mid=%s снесена (если была)." % MID)
conn.close()
