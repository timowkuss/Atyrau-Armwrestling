"""
Чинит "зависшую" запись турнира в id_map: если соревнование было
синхронизировано ДО пересоздания базы (например, до перехода на Neon),
локальный sync_state.db всё ещё думает, что оно существует на сервере под
старым remote_id — а физически там 404 "Соревнование не найдено".

Скрипт:
1. Читает название/дату/место турнира из локальной armwrestling.db.
2. Удаляет устаревшую запись id_map (entity_type='competition').
3. Создаёт соревнование заново на сервере (Neon/Railway) и сохраняет
   новый корректный remote_id обратно в id_map.

После этого нажми в приложении «Синхронизировать» ещё раз — категории,
участники и матчи из очереди подхватят уже правильный remote_id турнира.

Запускать из папки desktop-app:

    python fix_stale_competition.py <tid>

Если <tid> не указан — берётся 1 (частый случай, если турнир один).
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sync.api_client import SyncApiClient
from sync.state import SyncState
from sync import config

BASE_DIR = Path(__file__).resolve().parent
TOURNAMENT_DB = BASE_DIR / "armwrestling.db"

tid = int(sys.argv[1]) if len(sys.argv) > 1 else 1

if not TOURNAMENT_DB.exists():
    raise SystemExit(f"Не найден {TOURNAMENT_DB} — запусти скрипт из папки desktop-app")

conn = sqlite3.connect(str(TOURNAMENT_DB))
conn.row_factory = sqlite3.Row
row = conn.execute(
    "SELECT name, date, location FROM tournaments WHERE id=?", (tid,)
).fetchone()
conn.close()

if row is None:
    raise SystemExit(f"Турнир с id={tid} не найден в armwrestling.db")

print(f"Турнир: {row['name']!r}, дата={row['date']!r}, место={row['location']!r}")

state = SyncState()

old_remote = state.map_get("competition", tid)
print(f"Старый (битый) remote_id соревнования: {old_remote}")

with state._lock:
    state.conn.execute(
        "DELETE FROM id_map WHERE entity_type='competition' AND local_id=?", (tid,)
    )
    state.conn.commit()
print("Устаревшая запись id_map удалена.")

api = SyncApiClient()
print(f"Создаю соревнование заново на {config.API_BASE_URL} ...")
remote = api.create_competition(row["name"], row["date"], row["location"])
new_remote_id = remote["id"]

state.map_set("competition", tid, new_remote_id)
print(f"Готово. Новый remote_id соревнования: {new_remote_id}")
print("Теперь нажми в приложении «Синхронизировать» ещё раз.")
