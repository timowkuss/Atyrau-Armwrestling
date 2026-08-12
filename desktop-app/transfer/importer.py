"""Импорт соревнования из файла `.armwrestling`.

Безопасность импорта:
1. Файл открывается и проверяется (формат, checksum, версии, структура,
   связи, дубликаты) ДО любых изменений БД.
2. Все записи в локальную БД выполняются в одной транзакции
   (BEGIN IMMEDIATE ... COMMIT / ROLLBACK) — оборванный импорт не оставляет
   повреждённой БД.
3. Служебная БД синхронизации (id_map, очередь, competition_source)
   записывается в своей транзакции: только если основные данные легли.
4. Существующие id (competition_id, категории, участники, матчи,
   спортсмены, клубы, тренеры, операции очереди) сохраняются — повторная
   синхронизация не создаст дублей.
"""

import json
import os
import uuid

from .pack import read_archive, check_version, read_member_bytes


class CompetitionExistsError(Exception):
    """Соревнование с таким competition_id уже есть в локальной БД."""

    def __init__(self, tid, name, other_session):
        self.tid = tid
        self.name = name
        self.other_session = bool(other_session)
        super().__init__(f"Соревнование #{tid} «{name}» уже существует")


class IdCollisionError(Exception):
    """Экспортированные id (спортсмены/тренеры/клубы) заняты в этой БД."""

    def __init__(self, entity, ids):
        self.entity = entity
        self.ids = sorted(ids)
        super().__init__(
            f"Конфликт id: в локальной БД уже есть записи «{entity}» "
            f"с номерами {self.ids[:10]} — импорт невозможен без потери "
            "данных. Переносите соревнование на чистый компьютер "
            "(или в свежую установку приложения).")


class ImportValidationError(Exception):
    """Файл не прошёл проверку структуры/связей — импорт отменён."""


# ─── проверки файла (не трогают БД) ───────────────────────────────
def _unique_ids(rows, message):
    seen = {}
    for r in rows:
        i = r.get("id")
        if i is None:
            continue
        if i in seen:
            raise ImportValidationError(f"{message}: дубль id={i}")
        seen[i] = r
    return seen


def validate_archive(payload, metadata):
    """Проверяет структуру и связи внутри файла. Бросает
    ImportValidationError с первой найденной проблемой."""
    tid = metadata["competition_id"]
    tournament = payload["competition.json"]["tournament"]
    if tournament.get("id") != tid:
        raise ImportValidationError(
            "competition_id в metadata не совпадает с id внутри файла.")

    categories = _unique_ids(payload["categories.json"], "Категории")
    participants = _unique_ids(payload["participants.json"], "Участники")
    _unique_ids(payload["matches.json"], "Матчи")
    athlete_ids = {a["id"] for a in payload["athletes.json"]}
    club_ids = {c["id"] for c in payload["clubs.json"]}
    coach_ids = {c["id"] for c in payload["coaches.json"]}
    for a in payload["athletes.json"]:
        if a.get("coach_id") is not None and a["coach_id"] not in coach_ids:
            raise ImportValidationError(
                f"Спортсмен #{a['id']} ссылается на отсутствующего тренера "
                f"#{a['coach_id']}")
        if a.get("club_id") is not None and a["club_id"] not in club_ids:
            raise ImportValidationError(
                f"Спортсмен #{a['id']} ссылается на отсутствующий клуб "
                f"#{a['club_id']}")
    for c in payload["coaches.json"]:
        if c.get("club_id") is not None and c["club_id"] not in club_ids:
            raise ImportValidationError(
                f"Тренер #{c['id']} ссылается на отсутствующий клуб "
                f"#{c['club_id']}")

    for p in payload["participants.json"]:
        if p.get("tournament_id") != tid:
            raise ImportValidationError(f"Участник #{p['id']} чужого турнира")
        cid = p.get("category_id")
        if cid is not None and cid not in categories:
            raise ImportValidationError(
                f"Участник #{p['id']} ссылается на отсутствующую категорию "
                f"#{cid}")
        if p.get("athlete_id") is not None and \
                p["athlete_id"] not in athlete_ids:
            raise ImportValidationError(
                f"Участник #{p['id']} ссылается на отсутствующего спортсмена "
                f"#{p['athlete_id']}")

    done_results = set()
    for m in payload["matches.json"]:
        if m.get("tournament_id") != tid:
            raise ImportValidationError(f"Матч #{m['id']} чужого турнира")
        if m.get("category_id") not in categories:
            raise ImportValidationError(
                f"Матч #{m['id']} ссылается на отсутствующую категорию")
        for side in ("p1_id", "p2_id"):
            pid = m.get(side)
            if pid is not None and pid not in participants:
                raise ImportValidationError(
                    f"Матч #{m['id']}: участник {side} (#{pid}) отсутствует")
        winner = m.get("winner_id")
        if winner is not None and winner not in participants:
            raise ImportValidationError(
                f"Матч #{m['id']}: победитель #{winner} отсутствует")
        if m.get("status") not in ("pending", "done"):
            raise ImportValidationError(
                f"Матч #{m['id']}: недопустимый статус '{m.get('status')}'")
        if m.get("status") == "done":
            if winner is None:
                raise ImportValidationError(
                    f"Матч #{m['id']} завершён без победителя")
            done_results.add(m["id"])
            if winner not in (m.get("p1_id"), m.get("p2_id")):
                raise ImportValidationError(
                    f"Матч #{m['id']}: победитель не является участником")
        elif winner is not None:
            raise ImportValidationError(
                f"Матч #{m['id']} не завершён, но есть победитель")

    results = payload["results.json"]
    if {r["match_id"] for r in results} != done_results:
        raise ImportValidationError(
            "results.json не совпадает с завершёнными матчами")

    for o in payload["overrides.json"]:
        if o.get("tournament_id") != tid or \
                o.get("category_id") not in categories or \
                o.get("pid") not in participants:
            raise ImportValidationError(
                f"Двоеборье: override (категория #{o.get('category_id')}, "
                f"участник #{o.get('pid')}) ссылается на отсутствующие данные")

    for g in payload["bracket_generations.json"]:
        if g.get("category_id") not in categories:
            raise ImportValidationError(
                f"Сетка: категория #{g.get('category_id')} отсутствует")

    for h in payload["rating_events.json"].get("history", []):
        if h.get("tournament_id") != tid:
            raise ImportValidationError(
                f"Рейтинг: запись #{h.get('id')} чужого турнира")
        if h.get("club_id") is not None and h["club_id"] not in club_ids:
            raise ImportValidationError(
                f"Рейтинг: запись #{h.get('id')} ссылается на отсутствующий "
                f"клуб #{h['club_id']}")
        if h.get("athlete_id") is not None and \
                h["athlete_id"] not in athlete_ids:
            raise ImportValidationError(
                f"Рейтинг: запись #{h.get('id')} ссылается на отсутствующего "
                f"спортсмена #{h['athlete_id']}")

    _unique_ids(payload["sync_operations.json"], "Операции синхронизации")

    map_keys = set()
    for row in payload["id_map.json"]:
        key = (row.get("entity_type"), row.get("local_id"))
        if key in map_keys:
            raise ImportValidationError(f"id_map: дубль {key}")
        map_keys.add(key)


def preview_archive(src_path, password=None):
    """Открывает и проверяет файл, не трогая локальную БД.
    Возвращает (metadata, summary) для окна предпросмотра."""
    payload, metadata = read_archive(src_path, password)
    check_version(metadata)
    validate_archive(payload, metadata)
    counts = metadata.get("counts", {})
    summary = {
        "competition_id": metadata["competition_id"],
        "name": metadata.get("competition_name"),
        "date": payload["competition.json"]["tournament"].get("date"),
        "athletes": counts.get("athletes", 0),
        "coaches": counts.get("coaches", 0),
        "clubs": counts.get("clubs", 0),
        "categories": counts.get("categories", 0),
        "participants": counts.get("participants", 0),
        "matches": counts.get("matches", 0),
        "finished": counts.get("finished_matches", 0),
        "unfinished": counts.get("unfinished_matches", 0),
        "pending_operations": counts.get("pending_operations", 0),
        "last_modified_at": metadata.get("last_modified_at"),
        "created_at": metadata.get("created_at"),
        "encrypted": bool(metadata.get("encrypted")),
        "has_photos": bool(metadata.get("has_photos")),
        "session_id": metadata.get("session_id"),
    }
    return metadata, summary


# ─── проверки против локальной БД ─────────────────────────────────
_TABLE_BY_ENTITY = {"спортсмены": "athletes", "тренеры": "coaches",
                    "клубы": "clubs"}


def _check_id_collisions(conn, payload, force_replace=False):
    """Проверяет занятость экспортированных id спортсменов/тренеров/клубов.

    force_replace=True — это «восстановление из файла»: существующие записи
    с теми же id перезаписываются (INSERT OR REPLACE), конфликт не фатален.
    Возвращает списки id, которые будут перезаписаны."""
    overwrite = {table: [] for table in _TABLE_BY_ENTITY.values()}
    for entity, section in (("спортсмены", "athletes.json"),
                            ("тренеры", "coaches.json"),
                            ("клубы", "clubs.json")):
        rows = payload[section]
        if not rows:
            continue
        ids = sorted({r["id"] for r in rows})
        marks = ",".join("?" * len(ids))
        existing = [r[0] for r in conn.execute(
            f"SELECT id FROM {_TABLE_BY_ENTITY[entity]} WHERE id IN ({marks})",
            ids)]
        if existing and not force_replace:
            raise IdCollisionError(entity, existing)
        overwrite[_TABLE_BY_ENTITY[entity]] = existing
    return overwrite


# ─── запись в локальную БД ─────────────────────────────────────────
def _insert_rows(conn, table, rows):
    for r in rows:
        cols = list(r.keys())
        sql = (f"INSERT INTO {table} ({','.join(cols)}) "
               f"VALUES ({','.join('?' * len(cols))})")
        conn.execute(sql, tuple(r[c] for c in cols))


def _delete_competition_data(conn, tid):
    conn.execute("DELETE FROM club_rating_history WHERE tournament_id=?", (tid,))
    conn.execute("DELETE FROM matches WHERE tournament_id=?", (tid,))
    conn.execute("DELETE FROM participants WHERE tournament_id=?", (tid,))
    conn.execute("DELETE FROM dvoeborie_overrides WHERE tournament_id=?", (tid,))
    conn.execute("DELETE FROM weight_categories WHERE tournament_id=?", (tid,))
    conn.execute("DELETE FROM tournaments WHERE id=?", (tid,))


def _reseed_sequences(conn, tables):
    for table in tables:
        row = conn.execute(
            f"SELECT COALESCE(MAX(id), 0) AS m FROM {table}").fetchone()
        conn.execute(
            "INSERT OR REPLACE INTO sqlite_sequence (name, seq) VALUES (?,?)",
            (table, row[0]))


def _apply_photos(conn, payload, photo_map, photos_dir):
    """Переписывает photo_path у участников/спортсменов на локальные
    пути в photos_dir (файлы уже извлечены импортёром)."""
    if not photo_map:
        return
    for section, table in (("participants.json", "participants"),
                           ("athletes.json", "athletes")):
        for r in payload[section]:
            old = r.get("photo_path")
            if not old:
                continue
            archive_name = photo_map.get(old)
            if not archive_name:
                continue
            new_path = os.path.join(photos_dir, os.path.basename(archive_name))
            if os.path.exists(new_path):
                conn.execute(
                    f"UPDATE {table} SET photo_path=? WHERE id=?",
                    (new_path, r["id"]))


def _write_main_db(conn, payload, metadata, force_replace, photos_dir,
                   photo_map, overwrite_ids=None):
    tid = metadata["competition_id"]
    tournament = payload["competition.json"]["tournament"]
    new_session = uuid.uuid4().hex
    previous_session = tournament.get("session_id")

    if force_replace:
        _delete_competition_data(conn, tid)

    def write_entity(table, rows):
        """Спортсмены/тренеры/клубы: при restore перезаписываются, при
        обычном импорте (чистая БД) просто вставляются."""
        if force_replace and overwrite_ids and overwrite_ids.get(table):
            ids = set(overwrite_ids[table])
            for r in rows:
                if r["id"] in ids:
                    cols = list(r.keys())
                    sql = (f"INSERT OR REPLACE INTO {table} "
                           f"({','.join(cols)}) "
                           f"VALUES ({','.join('?' * len(cols))})")
                    conn.execute(sql, tuple(r[c] for c in cols))
                    continue
                cols = list(r.keys())
                sql = (f"INSERT INTO {table} ({','.join(cols)}) "
                       f"VALUES ({','.join('?' * len(cols))})")
                conn.execute(sql, tuple(r[c] for c in cols))
        else:
            _insert_rows(conn, table, rows)

    conn.execute(
        "INSERT INTO tournaments (id, weight_tolerance, name, date, location, "
        "bracket_system, format_type, status, finished_at, created_at, "
        "photo_folder, session_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (tid, tournament.get("weight_tolerance"), tournament["name"],
         tournament["date"], tournament.get("location"),
         tournament.get("bracket_system"), tournament.get("format_type"),
         tournament.get("status", "active"), tournament.get("finished_at"),
         tournament.get("created_at"), tournament.get("photo_folder"),
         new_session))

    cat_cols = ("id", "tournament_id", "name", "max_weight", "hand",
                "age_category", "gender", "is_plus")
    for r in payload["categories.json"]:
        conn.execute(
            f"INSERT INTO weight_categories ({','.join(cat_cols)}) "
            f"VALUES ({','.join('?' * len(cat_cols))})",
            tuple(r.get(c) for c in cat_cols))

    part_cols = ("id", "tournament_id", "name", "weight", "club",
                 "category_id", "hand", "photo_path", "age_category",
                 "athlete_id")
    for r in payload["participants.json"]:
        conn.execute(
            f"INSERT INTO participants ({','.join(part_cols)}) "
            f"VALUES ({','.join('?' * len(part_cols))})",
            tuple(r.get(c) for c in part_cols))

    match_cols = ("id", "tournament_id", "category_id", "hand", "round_name",
                  "bracket", "match_order", "p1_id", "p2_id", "winner_id",
                  "p1_losses", "p2_losses", "is_bye", "status", "win_next_id",
                  "win_next_slot", "lose_next_id", "lose_next_slot", "stage",
                  "table_number")
    for r in payload["matches.json"]:
        conn.execute(
            f"INSERT INTO matches ({','.join(match_cols)}) "
            f"VALUES ({','.join('?' * len(match_cols))})",
            tuple(r.get(c) for c in match_cols))

    write_entity("athletes", payload["athletes.json"])
    write_entity("coaches", payload["coaches.json"])
    write_entity("clubs", payload["clubs.json"])

    for r in payload["overrides.json"]:
        conn.execute(
            "INSERT INTO dvoeborie_overrides "
            "(tournament_id, category_id, pid, manual_rank) VALUES (?,?,?,?)",
            (r["tournament_id"], r["category_id"], r["pid"], r["manual_rank"]))

    for r in payload["bracket_generations.json"]:
        conn.execute(
            "INSERT OR REPLACE INTO bracket_generations "
            "(category_id, hand, generation) VALUES (?,?,?)",
            (r["category_id"], r["hand"], r["generation"]))

    for r in payload["rating_events.json"].get("club_rating", []):
        conn.execute(
            "INSERT OR REPLACE INTO club_rating (id, club_id, rating, "
            "updated_at) VALUES (?,?,?,?)",
            (r["id"], r["club_id"], r["rating"], r.get("updated_at")))

    hist_cols = ("id", "club_id", "athlete_id", "tournament_id", "points",
                 "reason", "description", "created_at")
    for r in payload["rating_events.json"].get("history", []):
        conn.execute(
            f"INSERT INTO club_rating_history ({','.join(hist_cols)}) "
            f"VALUES ({','.join('?' * len(hist_cols))})",
            tuple(r.get(c) for c in hist_cols))

    # Аккумуляторы клубного рейтинга пересчитываем из истории — импорт
    # переносит уже ПРИМЕНЁННЫЕ события (баллы = сумма событий), повторного
    # начисления быть не может.
    conn.execute(
        "UPDATE club_rating SET rating = COALESCE((SELECT SUM(points) "
        "FROM club_rating_history WHERE club_id = club_rating.club_id), 0), "
        "updated_at = datetime('now')")

    _apply_photos(conn, payload, photo_map, photos_dir)

    conn.execute(
        "INSERT INTO transfer_marks (tournament_id, previous_session_id, "
        "imported_from, imported_at) VALUES (?,?,?,datetime('now'))",
        (tid, previous_session, metadata.get("created_at")))

    _reseed_sequences(conn, ("tournaments", "weight_categories",
                             "participants", "matches", "athletes", "coaches",
                             "clubs", "club_rating", "club_rating_history"))


def _op_references_ids(payload, ids, tid):
    try:
        data = json.loads(payload)
    except Exception:
        return False
    if data.get("tid") == tid:
        return True
    for key in ("category_id", "cid", "pid", "mid", "aid", "tournament_id"):
        if data.get(key) in ids:
            return True
    return False


def _write_sync_state(state, payload, metadata, old_competition_ids):
    """Записывает id_map, pending-операции и competition_source в
    sync_state.db. Вызывается внутри транзакции state.conn."""
    tid = metadata["competition_id"]
    if old_competition_ids:
        old_ids = set(old_competition_ids)
        for row in state.conn.execute(
                "SELECT id, payload FROM pending_queue").fetchall():
            if _op_references_ids(row["payload"], old_ids, tid):
                state.conn.execute(
                    "DELETE FROM pending_queue WHERE id=?", (row["id"],))
    for row in payload["id_map.json"]:
        state.conn.execute(
            "INSERT OR REPLACE INTO id_map (entity_type, local_id, remote_id) "
            "VALUES (?,?,?)",
            (row["entity_type"], row["local_id"], row["remote_id"]))
    for op in payload["sync_operations.json"]:
        state.conn.execute(
            "INSERT OR IGNORE INTO pending_queue "
            "(id, operation, payload, created_at, attempts, last_error) "
            "VALUES (?,?,?,?,?,?)",
            (op["id"], op["operation"],
             json.dumps(op["payload"], ensure_ascii=False),
             op["created_at"], op.get("attempts", 0), op.get("last_error")))
    cs = payload["competition.json"].get("competition_source")
    if cs:
        state.conn.execute(
            "INSERT OR REPLACE INTO competition_source "
            "(local_id, name, date, location, weight_tolerance, "
            "bracket_system, format_type) VALUES (?,?,?,?,?,?,?)",
            (cs["local_id"], cs["name"], cs["date"], cs.get("location"),
             cs.get("weight_tolerance"), cs.get("bracket_system"),
             cs.get("format_type")))


# ─── главная точка входа ───────────────────────────────────────────
def import_competition(conn, state, src_path, password=None,
                       force_replace=False, photos_dir=None) -> dict:
    """Импортирует соревнование. Возвращает summary.

    - force_replace=False: если competition_id уже есть — CompetitionExistsError.
    - force_replace=True: данные существующего соревнования заменяются
      (внутри той же транзакции; старые данные восстанавливаемы из backup).
    """
    payload, metadata = read_archive(src_path, password)
    check_version(metadata)
    validate_archive(payload, metadata)

    tid = metadata["competition_id"]
    tournament = payload["competition.json"]["tournament"]

    existing = conn.execute(
        "SELECT id, name, session_id FROM tournaments WHERE id=?",
        (tid,)).fetchone()
    if existing is not None and not force_replace:
        raise CompetitionExistsError(
            tid, existing["name"],
            existing["session_id"] != tournament.get("session_id"))
    overwrite_ids = _check_id_collisions(conn, payload, force_replace)

    old_competition_ids = []
    if existing is not None:
        old_competition_ids = [r[0] for r in conn.execute(
            "SELECT id FROM weight_categories WHERE tournament_id=?", (tid,))]
        old_competition_ids += [r[0] for r in conn.execute(
            "SELECT id FROM participants WHERE tournament_id=?", (tid,))]
        old_competition_ids += [r[0] for r in conn.execute(
            "SELECT id FROM matches WHERE tournament_id=?", (tid,))]

    photo_map = metadata.get("photo_map") or {}
    if photo_map and photos_dir is None:
        raise ImportValidationError(
            "В файле есть фотографии, но не задана папка для их хранения.")
    if photo_map:
        if not os.path.exists(photos_dir):
            os.makedirs(photos_dir, exist_ok=True)
        salt = (bytes.fromhex(metadata["salt"])
                if metadata.get("encrypted") and metadata.get("salt") else b"")
        for archive_name in set(photo_map.values()):
            data = read_member_bytes(src_path, archive_name, password, salt)
            with open(os.path.join(photos_dir, os.path.basename(archive_name)),
                      "wb") as f:
                f.write(data)

    # Основная БД + служебная БД синхронизации: если любой шаг падает —
    # откатываются обе (в одном потоке это атомарно).
    conn.execute("BEGIN IMMEDIATE")
    try:
        _write_main_db(conn, payload, metadata, force_replace, photos_dir,
                       photo_map, overwrite_ids)
        if state is not None:
            with state._lock:
                try:
                    _write_sync_state(state, payload, metadata,
                                      old_competition_ids)
                    state.conn.commit()
                except Exception:
                    try:
                        state.conn.rollback()
                    except Exception:
                        pass
                    raise
        conn.execute("COMMIT")
    except Exception as e:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        if isinstance(e, (ImportValidationError, IdCollisionError,
                          CompetitionExistsError)):
            raise
        raise ImportValidationError(
            f"Импорт не удался, все изменения откачены: {e}") from e

    counts = metadata.get("counts", {})
    return {
        "competition_id": tid,
        "name": tournament["name"],
        "date": tournament.get("date"),
        "matches": counts.get("matches", 0),
        "finished": counts.get("finished_matches", 0),
        "unfinished": counts.get("unfinished_matches", 0),
        "pending_operations": counts.get("pending_operations", 0),
        "last_modified_at": metadata.get("last_modified_at"),
    }
