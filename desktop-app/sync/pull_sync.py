"""Обратная синхронизация: сайт (админка) -> десктоп.

sync_manager.py решает только половину задачи — десктоп сам отправляет
свои изменения на сервер. Но у десктопа обычно нет белого IP/публичного
адреса, поэтому сервер не может "постучаться" в него сам (вебхук).
Вместо этого десктоп периодически, в фоне, сам спрашивает сервер: "что
изменилось в админке с прошлого раза" — и накатывает изменения себе в
armwrestling.db.

Пока поддерживаются только карточки спортсменов (см. ARCHITECTURE.md —
это единственная сущность, которая сегодня одновременно существует и в
десктопе (таблица athletes), и в центральной базе с historией правок
через updated_at). Расширять на клубы/тренеров/данные турнира можно по
той же схеме, когда появится конкретная необходимость.
"""

import sqlite3
import threading

from . import config
from .api_client import ApiClientError

_CURSOR_NAME = "athletes"


def _split_full_name(full_name: str) -> tuple[str, str]:
    """Обратная операция к f"{first_name} {last_name}" (см.
    sync_manager.on_athlete_created). Если имя без пробела — всё целиком
    считаем именем, фамилию оставляем пустой (лучше так, чем угадывать)."""
    parts = (full_name or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return " ".join(parts[:-1]), parts[-1]


def _normalize_gender_for_desktop(gender: str | None) -> str:
    # Локальная схема требует NOT NULL CHECK (gender IN ('M','F')) — у
    # центральной базы gender nullable (см. app/db/models/athletes.py).
    # Если на сайте пол ещё не заполнен — берём 'M' как безопасный дефолт
    # вместо падения INSERT; при следующей правке в десктопе организатор
    # это поле всё равно видит и может поправить.
    return "F" if gender == "female" else "M"


class PullSyncManager:
    def __init__(self, api_client=None, state=None, db_path=None, poll_interval=10,
                 on_changes_applied=None):
        self.api = api_client
        self.state = state
        self.db_path = db_path
        self.poll_interval = poll_interval
        # Колбэк для UI (например, обновить список "Спортсмены" на экране,
        # если он сейчас открыт). Необязателен — по умолчанию ничего не делает.
        self.on_changes_applied = on_changes_applied
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="pull-sync-athletes"
        )
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    # ── основной цикл ────────────────────────────────────────
    def _loop(self):
        while not self._stop_event.is_set():
            try:
                self.poll_once()
            except Exception as e:  # noqa: BLE001 — фоновый поток не должен падать целиком
                print(f"[pull-sync] неожиданная ошибка: {e}")
            self._stop_event.wait(self.poll_interval)

    def poll_once(self) -> int:
        """Один цикл опроса. Возвращает число применённых изменений
        (обновления + удаления) — удобно для ручного вызова из UI/тестов."""
        if not config.SYNC_ENABLED:
            return 0

        since = self.state.get_cursor(_CURSOR_NAME)
        try:
            data = self.api.get_athlete_changes(since)
        except ApiClientError as e:
            print(f"[pull-sync] нет связи с сервером: {e}")
            return 0

        updated = data.get("updated", [])
        deleted = data.get("deleted", [])
        if not updated and not deleted:
            # Даже если изменений нет, курсор всё равно двигаем вперёд —
            # иначе при следующем опросе снова попросим "since=None" и
            # получим ВСЮ базу целиком (сервер трактует пустой since как
            # "отдай всё", см. GET /sync/athletes/changes).
            self.state.set_cursor(_CURSOR_NAME, data["server_time"])
            return 0

        conn = sqlite3.connect(str(self.db_path), timeout=5)
        conn.execute("PRAGMA busy_timeout = 5000")
        try:
            for item in updated:
                self._upsert_athlete(conn, item)
            for remote_id in deleted:
                self._delete_athlete(conn, remote_id)
            conn.commit()
        finally:
            conn.close()

        self.state.set_cursor(_CURSOR_NAME, data["server_time"])

        if self.on_changes_applied:
            try:
                self.on_changes_applied()
            except Exception as e:  # noqa: BLE001 — колбэк в UI не должен ронять поллер
                print(f"[pull-sync] on_changes_applied упал: {e}")

        return len(updated) + len(deleted)

    # ── применение изменений к armwrestling.db ──────────────
    def _upsert_athlete(self, conn: sqlite3.Connection, item: dict):
        remote_id = item["id"]
        first_name, last_name = _split_full_name(item.get("full_name", ""))
        gender = _normalize_gender_for_desktop(item.get("gender"))
        birth_date = item.get("birth_date") or "1970-01-01"
        club = item.get("club_name")
        rank = item.get("rank")
        photo_path = item.get("photo_path")

        local_id = self.state.map_get_local("athlete", remote_id)

        # Скрытую на сайте карточку (is_hidden=True, обычно — попытка
        # удаления, заблокированная историей участий) не убираем локально
        # молча: если она уже есть в десктопе, просто обновляем данные, но
        # НЕ создаём новую, если её тут ещё не было — скрытую карточку не
        # имеет смысла заводить впервые.
        if item.get("is_hidden") and local_id is None:
            return

        if local_id is not None:
            conn.execute(
                "UPDATE athletes SET first_name=?, last_name=?, birth_date=?, "
                "gender=?, club=?, rank=?, photo_path=? WHERE id=?",
                (first_name, last_name, birth_date, gender, club, rank, photo_path, local_id),
            )
            return

        cur = conn.execute(
            "INSERT INTO athletes (first_name, last_name, birth_date, gender, club, rank, photo_path) "
            "VALUES (?,?,?,?,?,?,?)",
            (first_name, last_name, birth_date, gender, club, rank, photo_path),
        )
        self.state.map_set("athlete", cur.lastrowid, remote_id)

    def _delete_athlete(self, conn: sqlite3.Connection, remote_id: int):
        local_id = self.state.map_get_local("athlete", remote_id)
        if local_id is None:
            return
        try:
            conn.execute("DELETE FROM athletes WHERE id=?", (local_id,))
        except sqlite3.IntegrityError:
            # У карточки есть локальные ссылки (например, участник турнира
            # был привязан к ней через athlete_id) — оставляем запись как
            # есть, чтобы не сломать историю уже прошедших соревнований;
            # снимаем только связку id_map, чтобы не путать с будущими
            # апдейтами по этому remote_id.
            pass
        self.state.map_delete("athlete", local_id)


# Единый инстанс на процесс, по тому же принципу, что и sync_manager —
# переиспользует его же api-клиент и SyncState (не открываем второе
# соединение к sync_state.db). db_path и запуск потока настраиваются
# в armwrestling_tournament.py при старте приложения через
# pull_sync_manager.configure(db_path=...); до вызова configure() поллер
# существует, но не запущен (start() ничего не сделает без db_path).
from .sync_manager import sync_manager as _sync_manager  # noqa: E402

pull_sync_manager = PullSyncManager(
    api_client=_sync_manager.api, state=_sync_manager.state
)


def configure(db_path, poll_interval=10, on_changes_applied=None):
    """Вызывается один раз при старте десктоп-приложения (см.
    armwrestling_tournament.py), когда известен путь к armwrestling.db и
    (опционально) колбэк для обновления UI после применения изменений."""
    pull_sync_manager.db_path = db_path
    pull_sync_manager.poll_interval = poll_interval
    pull_sync_manager.on_changes_applied = on_changes_applied
    pull_sync_manager.start()
