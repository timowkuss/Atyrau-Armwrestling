"""Обратная синхронизация: сайт (админка) -> десктоп.

sync_manager.py решает только половину задачи — десктоп сам отправляет
свои изменения на сервер. Но у десктопа обычно нет белого IP/публичного
адреса, поэтому сервер не может "постучаться" в него сам (вебхук).
Вместо этого десктоп периодически, в фоне, сам спрашивает сервер: "что
изменилось в админке с прошлого раза" — и накатывает изменения себе в
armwrestling.db.

Поддерживаются карточки спортсменов И тренеров (обе сущности одновременно
существуют и в десктопе — таблицы athletes/coaches, — и в центральной базе
с историей правок через updated_at). Тренеры опрашиваются ПЕРЕД
спортсменами в каждом цикле — так у только что подтянутого/переименованного
тренера уже есть актуальная запись в локальной таблице coaches к моменту,
когда до него доберётся привязка через athlete["coach_name"] (см.
_resolve_local_coach_id)."""

import sqlite3
import threading
from datetime import datetime

from . import config
from .api_client import ApiClientError

_CURSOR_ATHLETES = "athletes"
_CURSOR_COACHES = "coaches"
def _to_desktop_date(value: str | None) -> str:
    """Центральная база отдаёт birth_date в ISO (ГГГГ-ММ-ДД —
    a.birth_date.isoformat() на сервере), а вся остальная десктоп-логика
    (форма спортсмена, compute_age_category, список "Спортсмены") ждёт
    ДД.ММ.ГГГГ и делает birth_date.split("."). Раньше ISO-строка писалась
    в armwrestling.db как есть — из-за этого открытие списка спортсменов
    падало с ValueError на первом же спортсмене, изменённом через сайт."""
    s = (value or "").strip()
    if not s:
        return "01.01.1970"
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        pass
    try:
        # уже в нужном формате — просто проверяем, что он валиден
        datetime.strptime(s, "%d.%m.%Y")
        return s
    except ValueError:
        print(f"[pull-sync] нераспознанный формат birth_date от сервера: {s!r}, беру 01.01.1970")
        return "01.01.1970"


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


def _to_founded_year(value) -> int | None:
    """Сервер отдаёт founded_date как ISO 'ГГГГ-ММ-ДД'; десктоп хранит
    только founded_year (INTEGER) — берём первые 4 символа как год."""
    if not value:
        return None
    try:
        return int(str(value).strip()[:4])
    except (TypeError, ValueError):
        return None


class PullSyncManager:
    def __init__(self, api_client=None, state=None, db_path=None, poll_interval=10,
                 on_changes_applied=None):
        self.api = api_client
        self.state = state
        self.db_path = db_path
        self.poll_interval = poll_interval
        # Колбэк для UI (например, обновить список "Спортсмены"/"Тренеры"
        # на экране, если он сейчас открыт). Необязателен — по умолчанию
        # ничего не делает.
        self.on_changes_applied = on_changes_applied
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="pull-sync"
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
        (обновления + удаления, спортсмены + тренеры + клубы) — удобно для
        ручного вызова из UI/тестов."""
        if not config.SYNC_ENABLED:
            return 0

        applied = 0
        conn = sqlite3.connect(str(self.db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        try:
            # Каждый поллёр оборачиваем отдельно: сбой одной сущности
            # (например, временное падение/деплой сервера) не должен ронять
            # весь цикл и лишать синхронизации остальных.
            for poller in (self._poll_clubs, self._poll_coaches, self._poll_athletes):
                try:
                    applied += poller(conn)
                except Exception as e:  # noqa: BLE001
                    print(f"[pull-sync] {poller.__name__}: {e}")
        finally:
            conn.close()

        if applied and self.on_changes_applied:
            try:
                self.on_changes_applied()
            except Exception as e:  # noqa: BLE001 — колбэк в UI не должен ронять поллер
                print(f"[pull-sync] on_changes_applied упал: {e}")

        return applied

    # ── клубы ────────────────────────────────────────────────
    def _poll_clubs(self, conn: sqlite3.Connection) -> int:
        """Клубов немного — сервер отдаёт весь список целиком (GET /sync/clubs),
        без курсора. Апдейтим локальные клубы, которых у нас нет — заводим.
        Логотип/город/дата основания, изменённые в админке сайта, доезжают
        до десктопа именно так (раньше клубы вообще не подтягивались)."""
        try:
            clubs = self.api.get_clubs()
        except ApiClientError as e:
            print(f"[pull-sync] клубы: нет связи с сервером: {e}")
            return 0

        applied = 0
        for item in clubs or []:
            if self._upsert_club(conn, item):
                applied += 1
        if applied:
            conn.commit()
        return applied

    def _upsert_club(self, conn: sqlite3.Connection, item: dict) -> bool:
        remote_id = item["id"]
        name = (item.get("name") or "").strip()
        city = item.get("city_name")
        address = item.get("address")
        founded_year = _to_founded_year(item.get("founded_date"))
        logo_path = item.get("logo_path")

        local_id = self.state.map_get_local("club", remote_id)
        if local_id is not None:
            return self._apply_club(conn, local_id, name, city, address,
                                    founded_year, logo_path, remote_id=remote_id)

        # Клуб мог уже существовать локально под этим же именем (создан в
        # десктопе и ещё не успел уйти на сервер) — сопоставляем по имени,
        # чтобы не наплодить дублей.
        row = conn.execute(
            "SELECT id FROM clubs WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if row is not None:
            return self._apply_club(conn, row[0], name, city, address,
                                    founded_year, logo_path, remote_id=remote_id)

        cur = conn.execute(
            "INSERT INTO clubs (name, city, address, founded_year, logo_path) "
            "VALUES (?,?,?,?,?)",
            (name, city, address, founded_year, logo_path),
        )
        self.state.map_set("club", cur.lastrowid, remote_id)
        return True

    def _apply_club(self, conn: sqlite3.Connection, local_id: int, name, city,
                    address, founded_year, logo_path, remote_id: int) -> bool:
        row = conn.execute(
            "SELECT name, city, address, founded_year, logo_path FROM clubs WHERE id=?",
            (local_id,),
        ).fetchone()
        current = (row["name"], row["city"], row["address"], row["founded_year"], row["logo_path"])
        new = (name, city, address, founded_year, logo_path)
        if current == new:
            self.state.map_set("club", local_id, remote_id)
            return False
        conn.execute(
            "UPDATE clubs SET name=?, city=?, address=?, founded_year=?, logo_path=? WHERE id=?",
            (name, city, address, founded_year, logo_path, local_id),
        )
        self.state.map_set("club", local_id, remote_id)
        return True

    # ── тренеры ───────────────────────────────────────────────
    def _poll_coaches(self, conn: sqlite3.Connection) -> int:
        since = self.state.get_cursor(_CURSOR_COACHES)
        try:
            data = self.api.get_coach_changes(since)
        except ApiClientError as e:
            print(f"[pull-sync] тренеры: нет связи с сервером: {e}")
            return 0

        updated = data.get("updated", [])
        deleted = data.get("deleted", [])
        if not updated and not deleted:
            # Курсор двигаем всегда, даже без изменений — иначе следующий
            # опрос снова уйдёт с since=None и получит всю таблицу целиком
            # (сервер трактует пустой since как "отдай всё").
            self.state.set_cursor(_CURSOR_COACHES, data["server_time"])
            return 0

        for item in updated:
            self._upsert_coach(conn, item)
        for remote_id in deleted:
            self._delete_coach(conn, remote_id)
        conn.commit()

        self.state.set_cursor(_CURSOR_COACHES, data["server_time"])
        return len(updated) + len(deleted)

    def _upsert_coach(self, conn: sqlite3.Connection, item: dict):
        remote_id = item["id"]
        full_name = (item.get("full_name") or "").strip()
        club = item.get("club_name")
        photo_path = item.get("photo_path")
        bio = item.get("bio")
        first_name = item.get("first_name")
        last_name = item.get("last_name")
        birth_date = _to_desktop_date(item.get("birth_date")) if item.get("birth_date") else None
        iin = item.get("iin")
        qualification = item.get("qualification")
        city = item.get("city_name")
        phone = item.get("phone")

        local_id = self.state.map_get_local("coach", remote_id)
        if local_id is not None:
            conn.execute(
                "UPDATE coaches SET full_name=?, club=?, photo_path=?, bio=?, "
                "first_name=?, last_name=?, birth_date=?, iin=?, qualification=?, city=?, phone=? WHERE id=?",
                (full_name, club, photo_path, bio, first_name, last_name,
                 birth_date, iin, qualification, city, phone, local_id),
            )
            return

        # Тренер мог уже существовать локально под этим же именем (создан
        # в десктопе и ещё не успел уйти на сервер, либо был создан здесь
        # же через athlete.coach_name раньше, чем добрался до него этот
        # опрос) — сопоставляем по имени, чтобы не наплодить дублей.
        row = conn.execute(
            "SELECT id FROM coaches WHERE full_name = ? COLLATE NOCASE", (full_name,)
        ).fetchone()
        if row is not None:
            local_id = row[0]
            conn.execute(
                "UPDATE coaches SET full_name=?, club=?, photo_path=?, bio=?, "
                "first_name=?, last_name=?, birth_date=?, iin=?, qualification=?, city=?, phone=? WHERE id=?",
                (full_name, club, photo_path, bio, first_name, last_name,
                 birth_date, iin, qualification, city, phone, local_id),
            )
            self.state.map_set("coach", local_id, remote_id)
            return

        cur = conn.execute(
            "INSERT INTO coaches (full_name, club, photo_path, bio, first_name, "
            "last_name, birth_date, iin, qualification, city, phone) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (full_name, club, photo_path, bio, first_name, last_name,
             birth_date, iin, qualification, city, phone),
        )
        self.state.map_set("coach", cur.lastrowid, remote_id)

    def _delete_coach(self, conn: sqlite3.Connection, remote_id: int):
        local_id = self.state.map_get_local("coach", remote_id)
        if local_id is None:
            return
        # Отвязываем учеников локально (как и на сервере — ondelete=SET
        # NULL), затем удаляем самого тренера.
        conn.execute("UPDATE athletes SET coach_id=NULL WHERE coach_id=?", (local_id,))
        conn.execute("DELETE FROM coaches WHERE id=?", (local_id,))
        self.state.map_delete("coach", local_id)

    # ── спортсмены ────────────────────────────────────────────
    def _poll_athletes(self, conn: sqlite3.Connection) -> int:
        since = self.state.get_cursor(_CURSOR_ATHLETES)
        try:
            data = self.api.get_athlete_changes(since)
        except ApiClientError as e:
            print(f"[pull-sync] спортсмены: нет связи с сервером: {e}")
            return 0

        updated = data.get("updated", [])
        deleted = data.get("deleted", [])
        if not updated and not deleted:
            self.state.set_cursor(_CURSOR_ATHLETES, data["server_time"])
            return 0

        for item in updated:
            self._upsert_athlete(conn, item)
        for remote_id in deleted:
            self._delete_athlete(conn, remote_id)
        conn.commit()

        self.state.set_cursor(_CURSOR_ATHLETES, data["server_time"])
        return len(updated) + len(deleted)

    def _resolve_local_coach_id(self, conn: sqlite3.Connection, coach_name: str | None):
        """ФИО тренера -> локальный id в таблице coaches. Сопоставление по
        имени (не по id_map), т.к. AthleteChangeItem с сервера несёт
        только текст coach_name, не central id тренера (см.
        app/schemas/sync.py::AthleteChangeItem на бэкенде). Обычно к этому
        моменту тренер уже подтянут через _poll_coaches этого же цикла;
        если нет (гонка/старые данные) — заводим локальную запись-заглушку
        по имени, она доразрешится в id_map при следующем опросе тренеров."""
        name = (coach_name or "").strip()
        if not name:
            return None
        row = conn.execute(
            "SELECT id FROM coaches WHERE full_name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if row is not None:
            return row[0]
        cur = conn.execute("INSERT INTO coaches (full_name) VALUES (?)", (name,))
        return cur.lastrowid

    def _upsert_athlete(self, conn: sqlite3.Connection, item: dict):
        remote_id = item["id"]
        first_name, last_name = _split_full_name(item.get("full_name", ""))
        gender = _normalize_gender_for_desktop(item.get("gender"))
        birth_date = _to_desktop_date(item.get("birth_date"))
        club = item.get("club_name")
        rank = item.get("rank")
        photo_path = item.get("photo_path")
        iin = item.get("iin")
        phone = item.get("phone")
        coach_id = self._resolve_local_coach_id(conn, item.get("coach_name"))

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
                "gender=?, club=?, rank=?, photo_path=?, coach_id=?, iin=?, phone=? WHERE id=?",
                (first_name, last_name, birth_date, gender, club, rank, photo_path,
                 coach_id, iin, phone, local_id),
            )
            return

        cur = conn.execute(
            "INSERT INTO athletes (first_name, last_name, birth_date, gender, club, "
            "rank, photo_path, coach_id, iin, phone) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (first_name, last_name, birth_date, gender, club, rank, photo_path, coach_id, iin, phone),
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
