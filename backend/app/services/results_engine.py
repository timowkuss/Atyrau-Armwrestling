from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models.matches import Match
from app.db.models.results import Result

"""
Пайплайн, которого раньше не было: до этого сервиса модель Result и
GET /public/competitions/{id}/results существовали, но НИЧЕГО в проекте
не писало в таблицу results, кроме app/db/seed_demo_data.py — то есть
места 1-2-3 нигде не считались по факту завершения сетки.

Ничего в существующей бизнес-логике (генерация сетки в десктопе,
apply_match_result/elo_engine, схема matches) не меняется — этот сервис
только ЧИТАЕТ уже готовую таблицу matches (она полностью синхронизируется
из десктопа как есть) и производит из неё места. Вызывается из
app/api/v1/sync/matches.py после того, как матч обновился — если сетка
категории/руки уже доигралась, места посчитаются и запишутся сами,
без каких-либо изменений на стороне десктопа.
"""


def _loser_id(m: Match) -> int | None:
    if m.winner_id is None or m.p1_id is None or m.p2_id is None:
        return None
    return m.p2_id if m.winner_id == m.p1_id else m.p1_id


def compute_standings(matches: list[Match]) -> list[tuple[int, int, str]] | None:
    """Считает места по уже имеющимся матчам одной категории+руки.

    Возвращает список (competition_participant_id, place, medal) или
    None, если решающий(е) матч(и) ещё не сыграны — рано считать.
    """
    if not matches:
        return None

    final_matches = [m for m in matches if m.bracket == "final"]

    if final_matches:
        # Гранд-финал (и, если была, переигровка). Берём самый поздний
        # по stage сыгранный матч — переигровка, если она была, всегда
        # переопределяет исход обычного гранд-финала.
        decisive = None
        for m in sorted(final_matches, key=lambda x: -x.stage):
            if m.status == "done" and m.winner_id and m.p1_id and m.p2_id:
                decisive = m
                break
        if decisive is None:
            return None  # финал ещё не сыгран
    else:
        # Обычная сетка на выбывание без нижней сетки — финал это
        # последний раунд верхней сетки.
        wb_matches = [m for m in matches if m.bracket == "winners"]
        if not wb_matches:
            return None
        last_stage = max(m.stage for m in wb_matches)
        decisive = next(
            (
                m for m in wb_matches
                if m.stage == last_stage and m.status == "done" and m.winner_id
            ),
            None,
        )
        if decisive is None:
            return None

    gold_id = decisive.winner_id
    silver_id = _loser_id(decisive)
    if gold_id is None or silver_id is None:
        return None

    placements: list[tuple[int, int, str]] = [(gold_id, 1, "gold"), (silver_id, 2, "silver")]

    lb_matches = [m for m in matches if m.bracket == "losers"]
    if lb_matches:
        last_lb_stage = max(m.stage for m in lb_matches)
        lb_final = next(
            (
                m for m in lb_matches
                if m.stage == last_lb_stage and m.status == "done" and m.winner_id
            ),
            None,
        )
        if lb_final is not None:
            bronze_id = _loser_id(lb_final)
            if bronze_id is not None:
                placements.append((bronze_id, 3, "bronze"))
    else:
        # Одиночное выбывание: бронза (общая) — проигравшие раунда
        # перед финалом, если такой раунд вообще был (от 4 участников).
        wb_matches = [m for m in matches if m.bracket == "winners"]
        earlier_stages = sorted(
            {m.stage for m in wb_matches if m.stage < decisive.stage}, reverse=True
        )
        if earlier_stages:
            semi_stage = earlier_stages[0]
            for m in wb_matches:
                if m.stage != semi_stage or m.status != "done" or not m.winner_id:
                    continue
                bronze_id = _loser_id(m)
                if bronze_id is not None:
                    placements.append((bronze_id, 3, "bronze"))

    return placements


def finalize_category_results(db: Session, category_id: int, hand: str) -> bool:
    """Пересчитывает и (идемпотентно) сохраняет результаты категории+руки,
    если сетка уже доигралась. Возвращает True, если результаты были
    записаны/обновлены, False — если считать ещё рано (нет смысла
    вызывающему коду что-то дополнительно делать в этом случае).

    Идемпотентно: старые Result для этой категории просто перезаписываются
    целиком, так что повторный вызов (или исправление результата задним
    числом) всегда приводит таблицу results к consistent-состоянию, а не
    плодит дубли.
    """
    matches = (
        db.query(Match)
        .filter(Match.category_id == category_id, Match.hand == hand)
        .all()
    )
    placements = compute_standings(matches)
    if placements is None:
        return False

    competition_id = matches[0].competition_id

    db.query(Result).filter(
        Result.competition_id == competition_id,
        Result.category_id == category_id,
    ).delete(synchronize_session=False)

    for participant_id, place, medal in placements:
        db.add(
            Result(
                competition_id=competition_id,
                category_id=category_id,
                competition_participant_id=participant_id,
                place=place,
                medal=medal,
            )
        )

    return True
