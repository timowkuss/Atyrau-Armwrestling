"""Система рейтинга клубов федерации (локальная, desktop).

Зеркало backend-сервиса (backend/app/services/club_rating.py), работает
напрямую с SQLite через conn объекта Database — без импорта GUI-модуля,
чтобы сервис можно было покрыть тестами без запуска интерфейса.

Правила (единые для сайта и десктопа):
- клуб начинает с rating = 0, rating никогда < 0 (клампим в 0), но
  история хранит реальные отрицательные дельты;
- каждое изменение пишется в club_rating_history той же транзакцией;
- защита от дублей: уникальный индекс (club_id, athlete_id,
  tournament_id, reason, description) — повторный add_points ничего
  не начисляет.

Начисление:
- +5   первое выступление спортсмена за клуб / возвращение после простоя;
- +10/+6/+3   место 1/2/3 в категории турнира;
- -5   неактивность более 6 месяцев (однократно);
- -10  спортсмен удалён из клуба.

Тренеры на рейтинг клуба НЕ влияют.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime

FIRST_PARTICIPATION_POINTS = 5
REMOVAL_POINTS = -10
INACTIVITY_POINTS = -5
PLACE_POINTS = {1: 10, 2: 6, 3: 3}
INACTIVE_MONTHS = 6

# Очки двоеборья за место на одной руке (таблица как в GUI-модуле).
DVOEBORIE_POINTS = {1: 10, 2: 7, 3: 5, 4: 4, 5: 3, 6: 2, 7: 1}

REASON_FIRST_PARTICIPATION = "FIRST_PARTICIPATION"
REASON_PLACE = "PLACE"
REASON_INACTIVITY = "INACTIVITY"
REASON_ATHLETE_REMOVED = "ATHLETE_REMOVED"

_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%Y %H:%M", "%d/%m/%Y")


def _parse_date(value):
    """Разбирает дату турнира/рождения в произвольном текстовом формате."""
    if not value:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def add_months(d, months):
    """d + months календарных месяцев (с учётом длины месяца)."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _ensure_rating(conn, club_id):
    row = conn.execute(
        "SELECT id, rating FROM club_rating WHERE club_id=?", (club_id,)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO club_rating (club_id, rating) VALUES (?, 0)", (club_id,)
        )
        return 0
    return row["rating"]


def add_points(conn, club_id, athlete_id, tournament_id, points, reason, description):
    """Начисляет points клубу и пишет запись в историю. Идемпотентно.

    Возвращает dict {"applied": bool, "rating": int}.
    """
    existing = conn.execute(
        "SELECT 1 FROM club_rating_history WHERE club_id=? AND athlete_id IS ? "
        "AND tournament_id IS ? AND reason=? AND description=?",
        (club_id, athlete_id, tournament_id, reason, description),
    ).fetchone()
    if existing is not None:
        cur_rating = conn.execute(
            "SELECT rating FROM club_rating WHERE club_id=?", (club_id,)
        ).fetchone()
        return {"applied": False, "rating": cur_rating["rating"] if cur_rating else 0}

    current = _ensure_rating(conn, club_id)
    new_rating = max(0, current + points)
    conn.execute(
        "UPDATE club_rating SET rating=?, updated_at=datetime('now') WHERE club_id=?",
        (new_rating, club_id),
    )
    conn.execute(
        "INSERT INTO club_rating_history "
        "(club_id, athlete_id, tournament_id, points, reason, description) "
        "VALUES (?,?,?,?,?,?)",
        (club_id, athlete_id, tournament_id, points, reason, description),
    )
    return {"applied": True, "rating": new_rating}


def _mark_attended(conn, athlete_id, competition_date):
    """Обновляет поля активности спортсмена после участия в турнире."""
    conn.execute(
        "UPDATE athletes SET club_active=1, last_competition_date=?, next_inactive_date=? "
        "WHERE id=?",
        (competition_date, add_months(competition_date, INACTIVE_MONTHS), athlete_id),
    )


def _record_participation(conn, participant, competition_date, tournament_id):
    """Первое участие / возвращение спортсмена за клуб: +5, активация.

    Повторное участие активного спортсмена +5 НЕ даёт (club_active уже
    true) — нельзя получать баллы за одного спортсмена бесконечно.
    """
    athlete_id = participant["athlete_id"]
    if not athlete_id:
        return
    athlete = conn.execute("SELECT * FROM athletes WHERE id=?", (athlete_id,)).fetchone()
    if athlete is None:
        return
    club_id = athlete["club_id"]
    if not club_id:
        # Снимка клуба на момент турнира в десктопе нет — используем
        # название клуба участника как fallback к реестру клубов.
        club_name = participant["club"]
        if club_name:
            club = conn.execute(
                "SELECT id FROM clubs WHERE lower(name)=lower(?)", (club_name,)
            ).fetchone()
            club_id = club["id"] if club else None
    if not club_id:
        _mark_attended(conn, athlete_id, competition_date)
        return
    if not athlete["club_active"]:
        add_points(
            conn,
            club_id,
            athlete_id,
            tournament_id,
            FIRST_PARTICIPATION_POINTS,
            REASON_FIRST_PARTICIPATION,
            "Первое участие спортсмена за клуб",
        )
    _mark_attended(conn, athlete_id, competition_date)


def _hand_standings(conn, tournament_id, category_id, hand):
    """Расстановка мест одной руки категории по матчам сетки.

    Логика как в DoubleEliminationEngine.get_standings GUI-модуля:
    чемпион — победитель финала, далее сортировка по глубине выбывания
    (stage) и числу побед.
    """
    matches = conn.execute(
        "SELECT * FROM matches WHERE tournament_id=? AND category_id=? AND hand=?",
        (tournament_id, category_id, hand),
    ).fetchall()
    if not matches:
        return []

    stats = {}

    def ensure(pid):
        if pid is None or pid in stats:
            return
        stats[pid] = {"pid": pid, "wins": 0, "losses": 0,
                      "eliminated": False, "elim_round_score": -1}

    for m in matches:
        ensure(m["p1_id"])
        ensure(m["p2_id"])
        if m["status"] in ("done", "bye") and m["winner_id"]:
            winner = m["winner_id"]
            loser = m["p2_id"] if winner == m["p1_id"] else m["p1_id"]
            if m["status"] == "done":
                ensure(winner)
                stats[winner]["wins"] += 1
                if loser:
                    ensure(loser)
                    stats[loser]["losses"] += 1
                    if m["stage"] > stats[loser]["elim_round_score"]:
                        stats[loser]["elim_round_score"] = m["stage"]
                        stats[loser]["eliminated"] = True

    if not stats:
        return []

    final_matches = [m for m in matches
                     if m["win_next_id"] is None and m["status"] == "done"]
    champion = None
    if final_matches:
        last = max(final_matches, key=lambda m: m["stage"])
        champion = last["winner_id"]
        if champion in stats:
            stats[champion]["eliminated"] = False
            stats[champion]["elim_round_score"] = 9999

    ordered = sorted(
        stats.values(),
        key=lambda s: (
            0 if s["pid"] == champion else 1,
            -s["elim_round_score"],
            s["losses"],
        ),
    )
    return [{"participant_id": s["pid"], "place": i + 1} for i, s in enumerate(ordered)]


def _category_standings(conn, tournament_id, category):
    """Итоговые места категории (двоеборье, если сыграны обе руки).

    Место на каждой руке переводится в очки двоеборья, очки суммируются,
    по убыванию суммы строится расстановка (как compute_dvoeborie_standings
    в GUI). Тай-брейк при равных очках — меньший вес; при равных очках
    И весе спортсмены делят одно место.
    """
    rows_ = conn.execute(
        "SELECT DISTINCT hand FROM matches WHERE tournament_id=? AND category_id=? "
        "AND hand IS NOT NULL",
        (tournament_id, category["id"]),
    ).fetchall()
    hands = {r["hand"] for r in rows_}
    if not hands:
        hands = {"Правая", "Левая"} if category["hand"] == "Обе" else {category["hand"]}

    right = _hand_standings(conn, tournament_id, category["id"], "Правая") if "Правая" in hands else []
    left = _hand_standings(conn, tournament_id, category["id"], "Левая") if "Левая" in hands else []
    right_map = {s["participant_id"]: s["place"] for s in right}
    left_map = {s["participant_id"]: s["place"] for s in left}

    weights = {
        r["id"]: r["weight"]
        for r in conn.execute(
            "SELECT id, weight FROM participants WHERE tournament_id=? AND category_id=?",
            (tournament_id, category["id"]),
        ).fetchall()
    }

    pids = set(right_map) | set(left_map)
    if not pids:
        return []

    rows = []
    for pid in pids:
        r_place = right_map.get(pid)
        l_place = left_map.get(pid)
        r_pts = DVOEBORIE_POINTS.get(r_place, 0) if r_place else 0
        l_pts = DVOEBORIE_POINTS.get(l_place, 0) if l_place else 0
        rows.append({"participant_id": pid, "total_points": r_pts + l_pts,
                     "weight": weights.get(pid), "place": 0})

    def best_place(row):
        places = [x for x in (right_map.get(row["participant_id"]), left_map.get(row["participant_id"])) if x]
        return min(places) if places else 9999

    def weight_key(w):
        return w if w is not None else float("inf")

    rows.sort(key=lambda r: (-r["total_points"], weight_key(r["weight"]),
                             best_place(r), r["participant_id"]))

    place = 0
    prev_key = None
    for i, row in enumerate(rows):
        key = (row["total_points"], weight_key(row["weight"]))
        if key != prev_key:
            place = i + 1
            prev_key = key
        row["place"] = place
    return rows


def finalize_competition(conn, tournament_id):
    """Начисляет рейтинг клубов по итогам завершённого турнира.

    Вызывается при завершении турнира (и при синхронизации его статуса).
    Идемпотентно: повторный вызов ничего не задваивает благодаря
    уникальному индексу истории. Призёрам (1-3) — очки за место, каждому
    зарегистрированному участнику — первое участие/возвращение (+5).
    """
    tournament = conn.execute(
        "SELECT * FROM tournaments WHERE id=?", (tournament_id,)
    ).fetchone()
    if tournament is None:
        return {"status": "not found"}
    if tournament["status"] != "finished":
        return {"status": "skipped", "reason": "not finished"}

    competition_date = _parse_date(tournament["date"]) or date.today()
    categories = conn.execute(
        "SELECT * FROM weight_categories WHERE tournament_id=? ORDER BY max_weight",
        (tournament_id,),
    ).fetchall()

    place_records = 0
    for category in categories:
        standings = _category_standings(conn, tournament_id, category)
        participants = conn.execute(
            "SELECT * FROM participants WHERE tournament_id=? AND category_id=?",
            (tournament_id, category["id"]),
        ).fetchall()
        participants_by_pid = {p["id"]: p for p in participants}

        for row in standings:
            participant = participants_by_pid.get(row["participant_id"])
            if participant is None:
                continue
            place = row["place"]
            if place <= 3 and place in PLACE_POINTS:
                athlete_id = participant["athlete_id"]
                # Клуб участника (по спортсмену или по названию клуба).
                club_id = None
                if athlete_id:
                    athlete = conn.execute(
                        "SELECT club_id FROM athletes WHERE id=?", (athlete_id,)
                    ).fetchone()
                    club_id = athlete["club_id"] if athlete else None
                if not club_id and participant["club"]:
                    club = conn.execute(
                        "SELECT id FROM clubs WHERE lower(name)=lower(?)",
                        (participant["club"],),
                    ).fetchone()
                    club_id = club["id"] if club else None
                if club_id:
                    label = f"{place} место · {category['name']}"
                    add_points(
                        conn,
                        club_id,
                        athlete_id,
                        tournament_id,
                        PLACE_POINTS[place],
                        REASON_PLACE,
                        label,
                    )
                    place_records += 1

        for participant in participants:
            _record_participation(conn, participant, competition_date, tournament_id)

    conn.commit()
    return {"status": "ok", "place_records": place_records}


def apply_athlete_removed(conn, athlete_id, club_id):
    """Штраф -10 клубу за удаление спортсмена из клуба."""
    if not club_id:
        return
    add_points(
        conn,
        club_id,
        athlete_id,
        None,
        REMOVAL_POINTS,
        REASON_ATHLETE_REMOVED,
        "Спортсмен удалён из клуба",
    )


def mark_joined(conn, athlete_id):
    """Отмечает дату вступления спортсмена в клуб (join_club_date)."""
    conn.execute(
        "UPDATE athletes SET join_club_date=COALESCE(join_club_date, date('now')) "
        "WHERE id=?",
        (athlete_id,),
    )
    conn.commit()


def check_inactive_athletes(conn, today=None):
    """Однократный штраф -5 за неактивность (> 6 месяцев без турниров).

    Точечный запрос по next_inactive_date <= today AND club_active = 1 —
    без перебора всех спортсменов. После обработки club_active сбрасывается
    в 0, повторно спортсмен в выборку не попадёт.
    """
    today = today or date.today()
    rows = conn.execute(
        "SELECT * FROM athletes WHERE club_active=1 AND next_inactive_date IS NOT NULL "
        "AND next_inactive_date <= ?",
        (today.isoformat(),),
    ).fetchall()
    count = 0
    for athlete in rows:
        if athlete["club_id"]:
            add_points(
                conn,
                athlete["club_id"],
                athlete["id"],
                None,
                INACTIVITY_POINTS,
                REASON_INACTIVITY,
                "Спортсмен не участвовал более 6 месяцев",
            )
        conn.execute(
            "UPDATE athletes SET club_active=0, next_inactive_date=NULL WHERE id=?",
            (athlete["id"],),
        )
        count += 1
    if count:
        conn.commit()
    return count


def get_club_rating(conn, club_id):
    row = conn.execute(
        "SELECT rating FROM club_rating WHERE club_id=?", (club_id,)
    ).fetchone()
    return row["rating"] if row else 0


def get_club_rating_history(conn, club_id):
    return conn.execute(
        "SELECT h.*, "
        "CASE WHEN a.id IS NOT NULL THEN a.last_name || ' ' || a.first_name ELSE NULL END AS athlete_name, "
        "t.name AS tournament_name "
        "FROM club_rating_history h "
        "LEFT JOIN athletes a ON a.id = h.athlete_id "
        "LEFT JOIN tournaments t ON t.id = h.tournament_id "
        "WHERE h.club_id=? ORDER BY h.created_at DESC, h.id DESC",
        (club_id,),
    ).fetchall()


def recalc_club_rating_from_history(conn, club_id):
    """Пересобирает rating клуба как сумму истории (и клампит в 0)."""
    row = conn.execute(
        "SELECT COALESCE(SUM(points), 0) AS total FROM club_rating_history WHERE club_id=?",
        (club_id,),
    ).fetchone()
    rating = max(0, row["total"])
    _ensure_rating(conn, club_id)
    conn.execute(
        "UPDATE club_rating SET rating=?, updated_at=datetime('now') WHERE club_id=?",
        (rating, club_id),
    )
    conn.commit()
    return rating
