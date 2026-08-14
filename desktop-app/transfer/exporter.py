"""Экспорт соревнования в файл `.armwrestling`.

Полностью локальная операция: никаких сетевых вызовов, работает офлайн.
Сначала проверяется целостность соревнования, затем собирается снапшот,
считается checksum, файл записывается и перечитывается для проверки.
"""

import os
import uuid

from .pack import (DATABASE_SCHEMA_VERSION, EXPORT_VERSION, APP_VERSION,
                   checksum_members, compute_checksum, json_rows,
                   to_json_bytes, write_archive, read_archive, utc_now_iso)

_OP_ID_KEYS = ("tid", "category_id", "cid", "pid", "mid", "aid",
               "tournament_id", "participant_id", "match_id", "athlete_id")


class ExportError(Exception):
    """Соревнование невозможно экспортировать (повреждены данные)."""


def _ids(rows, key="id"):
    return {r[key] for r in rows if r.get(key) is not None}


def validate_competition_integrity(conn, tid: int) -> list:
    """Проверяет внутренние связи соревнования. Возвращает список проблем
    (пустой список — целостность в порядке)."""
    problems = []
    categories = {r["id"] for r in conn.execute(
        "SELECT id FROM weight_categories WHERE tournament_id=?", (tid,))}
    participants = {r["id"] for r in conn.execute(
        "SELECT id FROM participants WHERE tournament_id=?", (tid,))}

    for p in conn.execute(
            "SELECT id, category_id FROM participants WHERE tournament_id=?",
            (tid,)):
        if p["category_id"] is not None and p["category_id"] not in categories:
            problems.append(
                f"Участник #{p['id']} ссылается на несуществующую категорию "
                f"#{p['category_id']}")

    for m in conn.execute(
            "SELECT id, category_id, p1_id, p2_id, winner_id, status, is_bye, "
            "bracket "
            "FROM matches WHERE tournament_id=?", (tid,)):
        if m["category_id"] not in categories:
            problems.append(
                f"Матч #{m['id']} ссылается на несуществующую категорию "
                f"#{m['category_id']}")
        for side in ("p1_id", "p2_id"):
            pid = m[side]
            if pid is not None and pid not in participants:
                problems.append(
                    f"Матч #{m['id']}: участник {side} (#{pid}) не из этого "
                    "соревнования")
        if m["winner_id"] is not None and m["winner_id"] not in participants:
            problems.append(
                f"Матч #{m['id']}: победитель #{m['winner_id']} не из этого "
                "соревнования")
        if m["status"] not in ("pending", "waiting", "done", "bye"):
            problems.append(
                f"Матч #{m['id']}: недопустимый статус '{m['status']}'")
        if m["winner_id"] is not None and m["status"] not in ("done", "bye"):
            problems.append(
                f"Матч #{m['id']} ещё не завершён, но указан победитель")
        if m["status"] in ("done", "bye") and m["winner_id"] is None:
            # Ghost-матч: пустая ячейка сетки (нет ни одного участника) —
            # через неё прошли bye'и (см. _collapse_chained_byes), победителя
            # нет по определению. От флага is_bye не зависит.
            ghost = m["p1_id"] is None and m["p2_id"] is None
            if not ghost and m["bracket"] != "final":
                problems.append(f"Матч #{m['id']} завершён без победителя")
        if m["winner_id"] is not None and m["winner_id"] not in (m["p1_id"], m["p2_id"]):
            problems.append(
                f"Матч #{m['id']}: победитель #{m['winner_id']} не является "
                "участником матча")

    for o in conn.execute(
            "SELECT category_id, pid FROM dvoeborie_overrides "
            "WHERE tournament_id=?", (tid,)):
        if o["category_id"] not in categories or o["pid"] not in participants:
            problems.append(
                f"Двоеборье: override (категория #{o['category_id']}, "
                f"участник #{o['pid']}) ссылается на несуществующие данные")

    clubs = {r["id"] for r in conn.execute(
        "SELECT id FROM clubs")}
    for h in conn.execute(
            "SELECT id, club_id, athlete_id FROM club_rating_history "
            "WHERE tournament_id=?", (tid,)):
        if h["club_id"] is not None and h["club_id"] not in clubs:
            problems.append(
                f"Рейтинг: запись #{h['id']} ссылается на несуществующий "
                f"клуб #{h['club_id']}")

    return problems


def _photo_map_for(rows):
    """Строит {abs_path -> имя в архиве} и список бинарных фото для строк,
    у которых photo_path указывает на существующий локальный файл."""
    photo_map = {}
    files = {}
    for row in rows:
        path = row.get("photo_path")
        if not path:
            continue
        if str(path).startswith(("http://", "https://")):
            continue  # URL-фото не копируем
        if not os.path.exists(path):
            continue
        if path in photo_map:
            continue
        ext = os.path.splitext(path)[1] or ".jpg"
        name = f"photos/p{len(photo_map) + 1}{ext}"
        photo_map[path] = name
        with open(path, "rb") as f:
            files[name] = f.read()
    return photo_map, files


def collect_competition_data(conn, state, tid: int, include_photos: bool = False):
    """Собирает полный снапшот соревнования (все разделы архива).

    Возвращает dict: {payload: {раздел: список/dict}, metadata: {...},
    photo_files: {имя_в_архиве: bytes}}."""
    t = conn.execute(
        "SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
    if t is None:
        raise ExportError(f"Соревнование #{tid} не найдено в локальной БД.")

    categories = json_rows(conn.execute(
        "SELECT * FROM weight_categories WHERE tournament_id=?", (tid,)))
    participants = json_rows(conn.execute(
        "SELECT * FROM participants WHERE tournament_id=?", (tid,)))
    matches = json_rows(conn.execute(
        "SELECT * FROM matches WHERE tournament_id=?", (tid,)))
    overrides = json_rows(conn.execute(
        "SELECT * FROM dvoeborie_overrides WHERE tournament_id=?", (tid,)))

    cat_ids = _ids(categories)
    bracket_generations = []
    if cat_ids:
        marks = ",".join("?" * len(cat_ids))
        bracket_generations = json_rows(conn.execute(
            f"SELECT * FROM bracket_generations WHERE category_id IN ({marks})",
            sorted(cat_ids)))

    # Привязанные спортсмены: участники + история клубного рейтинга.
    athlete_ids = {p["athlete_id"] for p in participants
                   if p.get("athlete_id") is not None}
    athlete_ids |= {h["athlete_id"] for h in conn.execute(
        "SELECT DISTINCT athlete_id FROM club_rating_history "
        "WHERE tournament_id=?", (tid,)) if h["athlete_id"] is not None}
    athlete_ids -= {None}

    athletes = []
    coaches = []
    clubs = []
    coach_ids = set()
    club_ids = set()
    if athlete_ids:
        marks = ",".join("?" * len(athlete_ids))
        athletes = json_rows(conn.execute(
            f"SELECT * FROM athletes WHERE id IN ({marks})", sorted(athlete_ids)))
        coach_ids = {a["coach_id"] for a in athletes
                     if a.get("coach_id") is not None} - {None}
        club_ids = {a["club_id"] for a in athletes
                    if a.get("club_id") is not None} - {None}
    if coach_ids:
        marks = ",".join("?" * len(coach_ids))
        coaches = json_rows(conn.execute(
            f"SELECT * FROM coaches WHERE id IN ({marks})", sorted(coach_ids)))
        club_ids |= {c["club_id"] for c in coaches
                     if c.get("club_id") is not None} - {None}
    if club_ids:
        marks = ",".join("?" * len(club_ids))
        clubs = json_rows(conn.execute(
            f"SELECT * FROM clubs WHERE id IN ({marks})", sorted(club_ids)))

    # Рейтинговые события (клубный рейтинг): только история этого турнира.
    if club_ids:
        marks = ",".join("?" * len(club_ids))
        rating_rows = conn.execute(
            f"SELECT * FROM club_rating WHERE club_id IN ({marks})",
            sorted(club_ids)).fetchall()
    else:
        rating_rows = []
    rating_events = {
        "club_rating": json_rows(rating_rows),
        "history": json_rows(conn.execute(
            "SELECT * FROM club_rating_history WHERE tournament_id=?", (tid,))),
    }

    # Результаты: снапшот завершённых матчей.
    results = [{
        "match_id": m["id"],
        "category_id": m["category_id"],
        "hand": m["hand"],
        "p1_id": m["p1_id"],
        "p2_id": m["p2_id"],
        "winner_id": m["winner_id"],
    } for m in matches if m["status"] == "done"]

    # ── синхронизация: pending-операции и карта id (только соревнование) ──
    pending = []
    op_ids_keep = None
    try:
        pending_rows = state.pending() if state is not None else []
        if pending_rows:
            keep_vals = set(athlete_ids) | {tid}
            keep_vals |= cat_ids
            keep_vals |= {p["id"] for p in participants}
            keep_vals |= {m["id"] for m in matches}
            keep_vals |= {c["id"] for c in clubs}
            keep_vals |= {c["id"] for c in coaches}
            for row in pending_rows:
                try:
                    import json as _json
                    payload = _json.loads(row["payload"])
                except Exception:
                    continue
                if any(payload.get(k) in keep_vals for k in _OP_ID_KEYS):
                    pending.append({
                        "id": row["id"],
                        "operation": row["operation"],
                        "payload": payload,
                        "created_at": row["created_at"],
                        "attempts": row["attempts"],
                        "last_error": row["last_error"],
                    })
        if pending:
            op_ids_keep = max(p["id"] for p in pending)
    except Exception as e:
        print(f"[transfer] предупреждение: очередь не прочитана: {e}")

    id_map = []
    if state is not None:
        try:
            with state._lock:
                id_map_rows = state.conn.execute(
                    "SELECT * FROM id_map").fetchall()
            map_keep = {("competition", tid)}
            map_keep |= {("category", i) for i in cat_ids}
            map_keep |= {("participant", p["id"]) for p in participants}
            map_keep |= {("match", m["id"]) for m in matches}
            map_keep |= {("athlete", i) for i in athlete_ids}
            map_keep |= {("coach", i) for i in coach_ids}
            map_keep |= {("club", i) for i in club_ids}
            for r in id_map_rows:
                key = (r["entity_type"], r["local_id"])
                if key in map_keep:
                    id_map.append({"entity_type": r["entity_type"],
                                   "local_id": r["local_id"],
                                   "remote_id": r["remote_id"]})
                elif r["entity_type"] == "athlete_of_participant" and (
                        r["local_id"] in {p["id"] for p in participants}
                        or r["local_id"] in athlete_ids):
                    id_map.append({"entity_type": r["entity_type"],
                                   "local_id": r["local_id"],
                                   "remote_id": r["remote_id"]})
        except Exception as e:
            print(f"[transfer] предупреждение: id_map не прочитана: {e}")

    competition_source = None
    if state is not None:
        try:
            cs = state.get_competition_source(tid)
            if cs is not None:
                competition_source = {k: cs[k] for k in cs.keys()}
        except Exception as e:
            print(f"[transfer] предупреждение: competition_source: {e}")

    # ── фотографии (опционально) ──
    photo_map = {}
    photo_files = {}
    if include_photos:
        photo_map, photo_files = _photo_map_for(participants + athletes)

    tournament = {k: t[k] for k in t.keys()}
    session_id = tournament.get("session_id")
    if not session_id:
        session_id = uuid.uuid4().hex
        conn.execute("UPDATE tournaments SET session_id=? WHERE id=?",
                     (session_id, tid))
        conn.commit()
        tournament["session_id"] = session_id

    finished = sum(1 for m in matches if m["status"] == "done")
    last_modified = max(
        [t["created_at"] or ""] +
        [str(p["created_at"]) for p in pending])
    payload = {
        "competition.json": {
            "tournament": tournament,
            "competition_source": competition_source,
            "session_id": session_id,
        },
        "categories.json": categories,
        "participants.json": participants,
        "matches.json": matches,
        "athletes.json": athletes,
        "coaches.json": coaches,
        "clubs.json": clubs,
        "results.json": results,
        "rating_events.json": rating_events,
        "overrides.json": overrides,
        "bracket_generations.json": bracket_generations,
        "sync_operations.json": pending,
        "id_map.json": id_map,
    }
    metadata = {
        "export_id": uuid.uuid4().hex,
        "competition_id": tid,
        "competition_name": t["name"],
        "export_version": EXPORT_VERSION,
        "application_version": APP_VERSION,
        "database_schema_version": DATABASE_SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "last_modified_at": last_modified,
        "last_operation_id": op_ids_keep,
        "session_id": session_id,
        "has_photos": bool(photo_map),
        "photo_map": photo_map,
        "counts": {
            "athletes": len(athletes),
            "coaches": len(coaches),
            "clubs": len(clubs),
            "categories": len(categories),
            "participants": len(participants),
            "matches": len(matches),
            "finished_matches": finished,
            "unfinished_matches": len(matches) - finished,
            "pending_operations": len(pending),
        },
    }
    return {"payload": payload, "metadata": metadata,
            "photo_files": photo_files}


def export_competition(conn, state, tid: int, dest_path: str,
                       password: str | None = None, include_photos: bool = False,
                       emergency: bool = False) -> dict:
    """Экспортирует соревнование в dest_path. Возвращает metadata.

    emergency=True — пропускает проверку целостности (максимально быстро),
    но файл всё равно валиден и проверяется перечитыванием."""
    if not emergency:
        problems = validate_competition_integrity(conn, tid)
        if problems:
            raise ExportError(
                "Соревнование нельзя экспортировать: повреждены данные.\n- "
                + "\n- ".join(problems[:10]))

    data = collect_competition_data(conn, state, tid, include_photos)
    payload = {}
    for name, obj in data["payload"].items():
        payload[name] = to_json_bytes(obj)
    payload.update(data["photo_files"])

    metadata = data["metadata"]
    if password:
        # checksum считается по содержимому ДО шифрования: read_archive
        # расшифровывает разделы и сверяет checksum с расшифрованными байтами.
        metadata = dict(metadata)
        metadata["checksum"] = compute_checksum(checksum_members(payload))
        import secrets
        salt = secrets.token_bytes(16)
        encrypted = {}
        for name, raw in payload.items():
            from .pack import encrypt_payload
            encrypted[name] = encrypt_payload(raw, password, salt)
        payload = encrypted
        metadata["encrypted"] = True
        metadata["salt"] = salt.hex()

    write_archive(dest_path, payload, metadata)

    # Проверка: файл должен открываться и успешно проверяться.
    try:
        read_archive(dest_path, password)
    except Exception as e:
        raise ExportError(f"Экспорт не прошёл проверку: {e}")
    return metadata
