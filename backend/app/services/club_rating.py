"""Система рейтинга клубов федерации.

Единые правила для всех источников (backend, десктоп):

- Клуб начинает с rating = 0.
- rating никогда не бывает отрицательным (клампим в 0), но история
  (club_rating_history) хранит реальные, в т.ч. отрицательные, дельты.
- Каждое изменение обязательно записывается в историю (транзакцией
  вместе с обновлением club_rating).
- Защита от двойного начисления: история уникальна по
  (club_id, athlete_id, tournament_id, reason, description), повторный
  вызов add_points ничего не начисляет.

Начисление:
- +5  спортсмен впервые выступил за клуб (или вернулся после простоя);
- +10/+6/+3  место 1/2/3 в категории турнира;
- -5  спортсмен не участвовал более 6 месяцев (однократно);
- -10 спортсмен удалён из клуба.

Тренеры на рейтинг клуба НЕ влияют.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.athletes import Athlete
from app.db.models.categories import Category
from app.db.models.club_rating import ClubRating, ClubRatingHistory
from app.db.models.clubs import Club
from app.db.models.competitions import Competition, CompetitionParticipant
from app.db.models.dvoeborie_override import DvoeborieOverride
from app.db.models.matches import Match
from app.db.models.results import Result

# ─── Баллы ─────────────────────────────────────────────────────
FIRST_PARTICIPATION_POINTS = 5
REMOVAL_POINTS = -10
INACTIVITY_POINTS = -5
PLACE_POINTS = {1: 10, 2: 6, 3: 3}
INACTIVE_MONTHS = 6

# Двоеборье: перевод места на руке в очки двоеборья (как в десктопе).
DVOEBORIE_POINTS = {1: 10, 2: 7, 3: 5, 4: 4, 5: 3, 6: 2, 7: 1}

# Причины записей истории (стабильные ключи для защиты от дублей).
REASON_FIRST_PARTICIPATION = "FIRST_PARTICIPATION"
REASON_PLACE = "PLACE"
REASON_INACTIVITY = "INACTIVITY"
REASON_ATHLETE_REMOVED = "ATHLETE_REMOVED"


def add_months(d: date, months: int) -> date:
    """d + months календарных месяцев (с учётом длины месяца)."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _get_or_create_rating(db: Session, club_id: int) -> ClubRating:
    rating = db.query(ClubRating).filter(ClubRating.club_id == club_id).first()
    if rating is None:
        rating = ClubRating(club_id=club_id, rating=0)
        db.add(rating)
        db.flush()
    return rating


def _sync_club_points(db: Session, club_id: int, rating: int) -> None:
    """Держит денормализованную колонку clubs.rating_points в синхроне
    с club_rating.rating (по ней сортируются публичные списки клубов)."""
    club = db.get(Club, club_id)
    if club is not None:
        club.rating_points = rating


def add_points(
    db: Session,
    club_id: int,
    athlete_id: int | None,
    tournament_id: int | None,
    points: int,
    reason: str,
    description: str,
) -> dict:
    """Начисляет points клубу и пишет запись в историю. Идемпотентно:
    если запись с таким ключом уже есть — ничего не меняет.

    rating клампится в ноль: если клуб набирает штраф, превышающий его
    рейтинг, в club_rating сохраняется 0, а в истории — реальные -points.
    """
    existing = (
        db.query(ClubRatingHistory)
        .filter(
            ClubRatingHistory.club_id == club_id,
            ClubRatingHistory.athlete_id == athlete_id,
            ClubRatingHistory.tournament_id == tournament_id,
            ClubRatingHistory.reason == reason,
            ClubRatingHistory.description == description,
        )
        .first()
    )
    if existing is not None:
        return {"applied": False, "rating": existing.club.rating_points if existing.club else 0}

    rating_row = _get_or_create_rating(db, club_id)
    new_rating = max(0, rating_row.rating + points)
    rating_row.rating = new_rating
    rating_row.updated_at = datetime.now(timezone.utc)

    db.add(
        ClubRatingHistory(
            club_id=club_id,
            athlete_id=athlete_id,
            tournament_id=tournament_id,
            points=points,
            reason=reason,
            description=description,
        )
    )
    _sync_club_points(db, club_id, new_rating)
    db.flush()
    return {"applied": True, "rating": new_rating}


def _resolve_club(db: Session, participant: CompetitionParticipant) -> Club | None:
    """Клуб, которому идут очки за выступление спортсмена.

    Сначала — по снимку club_at_event (клуб на момент турнира), это
    исторически точно, даже если спортсмен потом сменил клуб. Если
    снимка нет — по текущему club_id спортсмена.
    """
    if participant.club_at_event and participant.club_at_event.strip():
        club = (
            db.query(Club)
            .filter(Club.name.ilike(participant.club_at_event.strip()))
            .first()
        )
        if club is not None:
            return club
    athlete = db.get(Athlete, participant.athlete_id)
    if athlete is not None and athlete.club_id:
        return db.get(Club, athlete.club_id)
    return None


def _mark_attended(db: Session, athlete: Athlete, competition: Competition) -> None:
    """Обновляет поля активности спортсмена после участия в турнире."""
    athlete.club_active = True
    athlete.last_competition_date = competition.date
    athlete.next_inactive_date = add_months(competition.date, INACTIVE_MONTHS)
    if not athlete.join_club_date:
        athlete.join_club_date = date.today()


def _record_participation(
    db: Session, participant: CompetitionParticipant, competition: Competition
) -> None:
    """Первое участие / возвращение спортсмена за клуб: +5, активация.

    Повторное участие активного спортсмена +5 НЕ даёт (club_active уже
    true) — нельзя получать бесконечные баллы за одного спортсмена.
    """
    athlete = db.get(Athlete, participant.athlete_id)
    if athlete is None:
        return
    club = _resolve_club(db, participant)
    if club is None:
        _mark_attended(db, athlete, competition)
        return
    if not athlete.club_active:
        add_points(
            db,
            club.id,
            athlete.id,
            competition.id,
            FIRST_PARTICIPATION_POINTS,
            REASON_FIRST_PARTICIPATION,
            "Первое участие спортсмена за клуб",
        )
    _mark_attended(db, athlete, competition)


# ─── Подсчёт мест по матчам (та же логика, что в десктопе) ─────
def _hand_standings(db: Session, competition_id: int, category_id: int, hand: str) -> list[dict]:
    """Расстановка мест для одной руки категории по матчам сетки.

    Логика повторяет SingleEliminationEngine/DoubleEliminationEngine
    get_standings из десктопа:
    - single elimination (до одного поражения): чемпион — победитель
      последнего сыгранного матча (в сетке SE нет bracket == "final",
      финальный матч тоже winners). Уникальные места по порядку выбывания:
      первый выбывший в своём раунде занимает нижнее место диапазона
      (для 8 участников: 1/4 -> 5,6,7,8; полуфинал -> 3,4; финал -> 2).
    - double elimination: победитель финала — чемпион, далее сортировка
      по глубине выбывания (elim_round_score) и числу побед.
    """
    matches = (
        db.query(Match)
        .filter(
            Match.competition_id == competition_id,
            Match.category_id == category_id,
            Match.hand == hand,
        )
        .all()
    )
    if not matches:
        return []

    stats: dict[int, dict] = {}

    def ensure(pid: int | None) -> None:
        if pid is None or pid in stats:
            return
        stats[pid] = {"pid": pid, "wins": 0, "losses": 0, "eliminated": False,
                      "elim_round_score": -1, "elim_order": 0}

    def round_score(match: Match) -> int:
        bracket_weight = {"winners": 0, "losers": 100, "final": 200}
        base = bracket_weight.get(match.bracket, 0)
        digits = "".join(ch for ch in (match.round_name or "") if ch.isdigit())
        return base + (int(digits) if digits else 0)

    has_loser_bracket = any(m.bracket == "losers" for m in matches)
    is_single = not has_loser_bracket

    for m in matches:
        ensure(m.p1_id)
        ensure(m.p2_id)
        if m.status in ("done", "bye") and m.winner_id:
            winner = m.winner_id
            loser = m.p2_id if winner == m.p1_id else m.p1_id
            if m.status == "done":
                ensure(winner)
                stats[winner]["wins"] += 1
                if loser:
                    ensure(loser)
                    stats[loser]["losses"] += 1
                    if is_single:
                        # В SE раунд = stage (0 = первый раунд, 1 = полуфинал, ...)
                        if m.stage > stats[loser]["elim_round_score"]:
                            stats[loser]["elim_round_score"] = m.stage
                            stats[loser]["elim_order"] = m.match_order
                            stats[loser]["eliminated"] = True
                    else:
                        rs = round_score(m)
                        if rs > stats[loser]["elim_round_score"]:
                            stats[loser]["elim_round_score"] = rs
                            stats[loser]["eliminated"] = True

    if not stats:
        return []

    champion = None
    runner_up = None
    if is_single:
        # Связи матчей (win_next_id) на сервер НЕ синкаются (всегда NULL),
        # поэтому финал SE определяем по структуре: done-матч с максимальным
        # stage во всей категории. Финал создаётся вместе с сеткой сразу,
        # так что его stage известен ещё до начала турнира.
        max_stage = max((m.stage for m in matches), default=-1)
        final_matches = [m for m in matches if m.stage == max_stage and m.status == "done"]
        if final_matches:
            last = max(final_matches, key=lambda m: m.match_order)
            champion = last.winner_id
            if champion in stats:
                stats[champion]["eliminated"] = False
                stats[champion]["elim_round_score"] = 9999
    else:
        gf_matches = [m for m in matches if m.bracket == "final" and m.status == "done"]
        if gf_matches:
            last_gf = gf_matches[-1]
            champion = last_gf.winner_id
            runner_up = last_gf.p2_id if champion == last_gf.p1_id else last_gf.p1_id
            if champion in stats:
                stats[champion]["eliminated"] = False
                stats[champion]["elim_round_score"] = 9999
            if runner_up in stats:
                stats[runner_up]["eliminated"] = True
                stats[runner_up]["elim_round_score"] = 99998

    if is_single:
        # Уникальные места по порядку выбывания: первый выбывший в своём
        # раунде занимает нижнее место диапазона (для 8 участников:
        # 1/4 -> 5,6,7,8; полуфинал -> 3,4; финал -> 2; чемпион -> 1).
        rounds = max((m.stage for m in matches), default=0) + 1
        by_round: dict[int, list] = {}
        for s in stats.values():
            if s["eliminated"]:
                by_round.setdefault(s["elim_round_score"], []).append(s)
        occupied: set[int] = set()
        placed: dict[int, int] = {}
        if champion is not None:
            placed[champion] = 1
            occupied.add(1)
        for st, lst in by_round.items():
            lst.sort(key=lambda s: (s["elim_order"], s["pid"]))
            max_place = 2 ** (rounds - st)
            for i, s in enumerate(lst):
                placed[s["pid"]] = max_place - i
                occupied.add(max_place - i)
        not_out = [s for s in stats.values()
                   if not s["eliminated"] and s["pid"] != champion]
        not_out.sort(key=lambda s: (-s["wins"], s["pid"]))
        free_place = 1
        for s in not_out:
            while free_place in occupied:
                free_place += 1
            placed[s["pid"]] = free_place
            occupied.add(free_place)
        ordered = sorted(stats.values(), key=lambda s: placed[s["pid"]])
        return [{"participant_id": s["pid"], "place": placed[s["pid"]]} for s in ordered]

    ordered = sorted(
        stats.values(),
        key=lambda s: (0 if s["pid"] == champion else 1, -s["elim_round_score"], -s["wins"]),
    )
    return [{"participant_id": s["pid"], "place": i + 1} for i, s in enumerate(ordered)]


def _category_standings(db: Session, competition: Competition, category: Category) -> list[dict]:
    """Итоговые места категории (двоеборье, если есть обе руки).

    Место на каждой руке переводится в очки двоеборья (DVOEBORIE_POINTS),
    очки суммируются, по убыванию суммы строится расстановка — ровно как
    compute_dvoeborie_standings в десктопе. Тай-брейк при равных очках —
    меньший вес (weight_at_event); равные очки И равный вес дают одно
    и то же место (спортивная конкурентная расстановка).
    """
    hands = {m.hand for m in db.query(Match).filter(
        Match.competition_id == competition.id,
        Match.category_id == category.id,
    ).all()}
    if not hands:
        hands = {"Правая", "Левая"} if category.hand == "Обе" else {category.hand}

    right = _hand_standings(db, competition.id, category.id, "Правая") if "Правая" in hands else []
    left = _hand_standings(db, competition.id, category.id, "Левая") if "Левая" in hands else []
    right_map = {s["participant_id"]: s["place"] for s in right}
    left_map = {s["participant_id"]: s["place"] for s in left}

    weights = {
        p.id: p.weight_at_event
        for p in db.query(CompetitionParticipant).filter(
            CompetitionParticipant.competition_id == competition.id,
            CompetitionParticipant.category_id == category.id,
        ).all()
    }

    manual_ranks = {
        o.participant_id: o.manual_rank
        for o in db.query(DvoeborieOverride).filter(
            DvoeborieOverride.competition_id == competition.id,
            DvoeborieOverride.category_id == category.id,
        ).all()
    }

    pids = set(right_map) | set(left_map)
    rows = []
    for pid in pids:
        r_place = right_map.get(pid)
        l_place = left_map.get(pid)
        r_pts = DVOEBORIE_POINTS.get(r_place, 0) if r_place else 0
        l_pts = DVOEBORIE_POINTS.get(l_place, 0) if l_place else 0
        rows.append(
            {"participant_id": pid, "total_points": r_pts + l_pts,
             "weight": weights.get(pid), "manual_rank": manual_ranks.get(pid),
             "place": 0}
        )

    def best_place(row: dict) -> int:
        places = [x for x in (right_map.get(row["participant_id"]), left_map.get(row["participant_id"])) if x]
        return min(places) if places else 9999

    def weight_key(w):
        return w if w is not None else float("inf")

    # Тай-брейк как в десктопе: больше очков — выше, при равных очках —
    # меньший вес; затем лучшее место на руке, затем id.
    rows.sort(key=lambda r: (-r["total_points"], weight_key(r["weight"]),
                             best_place(r), r["participant_id"]))

    # Внутри «спорной» группы (одинаковые очки и вес) выбранный жюри
    # победитель (manual_rank) поднимается в начало группы.
    if manual_ranks:
        ordered = []
        i = 0
        n = len(rows)
        while i < n:
            j = i
            while (j < n and rows[j]["total_points"] == rows[i]["total_points"]
                   and weight_key(rows[j]["weight"]) == weight_key(rows[i]["weight"])):
                j += 1
            group = rows[i:j]
            group.sort(key=lambda r: (r["manual_rank"] if r["manual_rank"] is not None else 1 << 30,
                                      best_place(r), r["participant_id"]))
            ordered.extend(group)
            i = j
        rows = ordered

    # Равные очки И равный вес делят одно место; спортсмен с manual_rank
    # внутри группы получает своё отдельное (более высокое) место.
    place = 0
    prev_key = None
    for i, row in enumerate(rows):
        key = (row["total_points"], weight_key(row["weight"]), row["manual_rank"])
        if key != prev_key:
            place = i + 1
            prev_key = key
        row["place"] = place
    return rows


def _upsert_result(
    db: Session, competition_id: int, category_id: int, participant_id: int, place: int
) -> None:
    result = (
        db.query(Result)
        .filter(
            Result.competition_id == competition_id,
            Result.category_id == category_id,
            Result.competition_participant_id == participant_id,
        )
        .first()
    )
    if result is None:
        medal = {1: "gold", 2: "silver", 3: "bronze"}.get(place, "none")
        db.add(
            Result(
                competition_id=competition_id,
                category_id=category_id,
                competition_participant_id=participant_id,
                place=place,
                medal=medal,
                points=PLACE_POINTS.get(place, 0),
            )
        )


def finalize_competition(db: Session, competition: Competition) -> dict:
    """Начисляет рейтинг клубов по итогам завершённого турнира.

    Вызывается при переходе статуса турнира в completed. Идемпотентно:
    повторный вызов ничего не задваивает (уникальность истории). Для
    каждой категории вычисляются итоговые места, сохраняются в results,
    призёрам (1-3) начисляются очки клубу, каждому участнику — первое
    участие/возвращение (+5).
    """
    if competition.status != "completed":
        return {"status": "skipped", "reason": "not completed"}

    categories = (
        db.query(Category).filter(Category.competition_id == competition.id).all()
    )
    place_records = 0
    for category in categories:
        standings = _category_standings(db, competition, category)
        participants = {
            p.id: p
            for p in db.query(CompetitionParticipant)
            .filter(CompetitionParticipant.category_id == category.id)
            .all()
        }
        # Места (1-3) — только по сыгравшим матчи (standings).
        for row in standings:
            participant = participants.get(row["participant_id"])
            if participant is None:
                continue
            place = row["place"]
            _upsert_result(db, competition.id, category.id, participant.id, place)

            if place <= 3 and place in PLACE_POINTS:
                club = _resolve_club(db, participant)
                if club is not None:
                    hand_label = _category_hands_label(db, competition, category)
                    add_points(
                        db,
                        club.id,
                        participant.athlete_id,
                        competition.id,
                        PLACE_POINTS[place],
                        REASON_PLACE,
                        f"{place} место · {category.name}{hand_label}",
                    )
                    place_records += 1

        # Участие (первое выступление/возвращение, +5) — для каждого
        # зарегистрированного участника категории, даже без матчей.
        for participant in participants.values():
            _record_participation(db, participant, competition)
    db.commit()

    # Пересчитываем агрегированную статистику спортсменов из фактических
    # матчей и мест завершённого турнира и фиксируем снимки elo-истории.
    from app.services.stats_engine import recalculate_all, record_elo_snapshots

    stats_count = recalculate_all(db)
    elo_records = record_elo_snapshots(db, competition)
    return {
        "status": "ok",
        "place_records": place_records,
        "stats_count": stats_count,
        "elo_records": elo_records,
    }


def _category_hands_label(db: Session, competition: Competition, category: Category) -> str:
    hands = {m.hand for m in db.query(Match).filter(
        Match.competition_id == competition.id,
        Match.category_id == category.id,
    ).all()}
    if len(hands) > 1:
        return " · двоеборье"
    if len(hands) == 1:
        return f" · {next(iter(hands))}"
    return ""


def apply_athlete_removed(db: Session, athlete_id: int, club_id: int | None) -> None:
    """Штраф -10 клубу за удаление спортсмена из клуба (reason ATHLETE_REMOVED)."""
    if club_id is None:
        return
    add_points(
        db,
        club_id,
        athlete_id,
        None,
        REMOVAL_POINTS,
        REASON_ATHLETE_REMOVED,
        "Спортсмен удалён из клуба",
    )


def mark_joined(db: Session, athlete_id: int) -> None:
    """Фиксирует дату вступления спортсмена в клуб, если её ещё нет."""
    athlete = db.get(Athlete, athlete_id)
    if athlete is not None and athlete.join_club_date is None:
        athlete.join_club_date = date.today()


def check_inactive_athletes(db: Session, today: date | None = None) -> int:
    """Однократный штраф -5 за неактивность (> 6 месяцев без турниров).

    Точечный запрос по next_inactive_date <= today AND club_active = true —
    без перебора всех спортсменов. Штраф применяется один раз: после
    обработки club_active сбрасывается в false, повторно такой спортсмен
    в выборку не попадёт. Вызывать: при запуске, после завершения
    турнира, при открытии профиля клуба.
    """
    today = today or date.today()
    athletes = (
        db.query(Athlete)
        .filter(Athlete.club_active.is_(True), Athlete.next_inactive_date <= today)
        .all()
    )
    count = 0
    for athlete in athletes:
        if athlete.club_id is not None:
            add_points(
                db,
                athlete.club_id,
                athlete.id,
                None,
                INACTIVITY_POINTS,
                REASON_INACTIVITY,
                "Спортсмен не участвовал более 6 месяцев",
            )
        athlete.club_active = False
        athlete.next_inactive_date = None
        count += 1
    if count:
        db.commit()
    return count


def get_club_rating(db: Session, club_id: int) -> int:
    row = db.query(ClubRating).filter(ClubRating.club_id == club_id).first()
    return row.rating if row else 0


def get_club_rating_history(db: Session, club_id: int) -> list[ClubRatingHistory]:
    return (
        db.query(ClubRatingHistory)
        .filter(ClubRatingHistory.club_id == club_id)
        .order_by(ClubRatingHistory.created_at.desc(), ClubRatingHistory.id.desc())
        .all()
    )


def recalc_club_rating_from_history(db: Session, club_id: int) -> int:
    """Вспомогательный инструмент: пересобирает rating клуба как сумму
    истории и синхронизирует clubs.rating_points. Полезно при первичном
    включении системы или ручном исправлении данных."""
    total = (
        db.query(func.coalesce(func.sum(ClubRatingHistory.points), 0))
        .filter(ClubRatingHistory.club_id == club_id)
        .scalar()
    ) or 0
    rating = max(0, total)
    row = _get_or_create_rating(db, club_id)
    row.rating = rating
    _sync_club_points(db, club_id, rating)
    db.commit()
    return rating
