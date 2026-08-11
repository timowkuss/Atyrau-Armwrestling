from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models.athletes import Athlete
from app.db.models.competitions import Competition, CompetitionParticipant
from app.db.models.elo_history import EloHistory
from app.db.models.matches import Match
from app.db.models.results import Result
from app.db.models.statistics import AthleteStatistic
from app.services.elo_engine import _hand_field, elo_combined

"""
Второй кусок пайплайна "турнир доигран -> данные на сайте актуальны"
(первый — app/services/results_engine.py, места 1-2-3). Модель
AthleteStatistic уже давно описывает total_wins/total_losses/gold_count
и т.д. и явно ссылается в докстринге на некий "stats_engine.py", который
должен их пересчитывать — но такого файла в проекте не было, эти поля
нигде не заполнялись за пределами seed_demo_data.py.

Как и elo_engine.py, стата пересчитывается ЦЕЛИКОМ по имеющимся matches/
results (а не инкрементально +1/-1) — так пересчёт идемпотентен и сам
себя чинит при любых исправлениях результатов задним числом, вместо
накопления рассинхрона. is_manual_override уважается точно так же, как
в elo_engine.py: если админ вручную поправил статистику, автопересчёт
эту карточку пропускает, пока override не снимут через
POST /admin/athletes/{id}/statistics/recalculate.
"""


def _get_or_create_stats(db: Session, athlete_id: int) -> AthleteStatistic:
    stats = (
        db.query(AthleteStatistic)
        .filter(AthleteStatistic.athlete_id == athlete_id)
        .first()
    )
    if stats is None:
        stats = AthleteStatistic(athlete_id=athlete_id)
        db.add(stats)
        db.flush()
    return stats


def recompute_athlete_statistics(db: Session, athlete_id: int) -> AthleteStatistic | None:
    """Пересчитывает статистику одного спортсмена с нуля. Возвращает
    обновлённый AthleteStatistic, либо None, если пересчёт пропущен
    (is_manual_override=True — карточка защищена от автопересчёта)."""
    stats = _get_or_create_stats(db, athlete_id)
    if stats.is_manual_override:
        return None

    participant_ids = [
        pid for (pid,) in db.query(CompetitionParticipant.id)
        .filter(CompetitionParticipant.athlete_id == athlete_id)
        .all()
    ]

    if not participant_ids:
        stats.total_competitions = 0
        stats.total_wins = 0
        stats.total_losses = 0
        stats.win_rate = 0.0
        stats.left_hand_wins = 0
        stats.left_hand_losses = 0
        stats.right_hand_wins = 0
        stats.right_hand_losses = 0
        stats.gold_count = 0
        stats.silver_count = 0
        stats.bronze_count = 0
        return stats

    matches = (
        db.query(Match)
        .filter(
            Match.status == "done",
            Match.is_bye.is_(False),
            Match.winner_id.isnot(None),
            or_(Match.p1_id.in_(participant_ids), Match.p2_id.in_(participant_ids)),
        )
        .all()
    )

    total_wins = total_losses = 0
    left_wins = left_losses = right_wins = right_losses = 0

    for m in matches:
        played = m.p1_id in participant_ids or m.p2_id in participant_ids
        if not played:
            continue
        won = m.winner_id in participant_ids
        field = _hand_field(m.hand)  # "elo_left" / "elo_right" / None

        if won:
            total_wins += 1
        else:
            total_losses += 1

        if field == "elo_left":
            if won:
                left_wins += 1
            else:
                left_losses += 1
        elif field == "elo_right":
            if won:
                right_wins += 1
            else:
                right_losses += 1
        # неопознанная рука (пустая/непонятная строка) — считаем только
        # в общий total, в разбивку по руке не попадает (см. elo_engine.py,
        # там та же логика: apply_match_result просто выходит без учёта Эло)

    gold = silver = bronze = 0
    results = (
        db.query(Result.place)
        .filter(Result.competition_participant_id.in_(participant_ids))
        .all()
    )
    for (place,) in results:
        if place == 1:
            gold += 1
        elif place == 2:
            silver += 1
        elif place == 3:
            bronze += 1

    total_competitions = (
        db.query(CompetitionParticipant.competition_id)
        .filter(CompetitionParticipant.athlete_id == athlete_id)
        .distinct()
        .count()
    )

    stats.total_competitions = total_competitions
    stats.total_wins = total_wins
    stats.total_losses = total_losses
    stats.win_rate = (
        round(total_wins / (total_wins + total_losses), 4)
        if (total_wins + total_losses) > 0
        else 0.0
    )
    stats.left_hand_wins = left_wins
    stats.left_hand_losses = left_losses
    stats.right_hand_wins = right_wins
    stats.right_hand_losses = right_losses
    stats.gold_count = gold
    stats.silver_count = silver
    stats.bronze_count = bronze

    return stats


def recalculate_all(db: Session) -> int:
    """Пересчитывает статистику всех спортсменов (кроме ручных оверрайдов).
    Возвращает число пересчитанных. Коммитит в конце."""
    athlete_ids = [aid for (aid,) in db.query(Athlete.id).all()]
    count = 0
    for aid in athlete_ids:
        if recompute_athlete_statistics(db, aid) is not None:
            count += 1
    db.commit()
    return count


def record_elo_snapshots(db: Session, competition: Competition) -> int:
    """Фиксирует снимок elo спортсменов после завершённого турнира — по
    левой руке, правой и суммарному рейтингу (обе руки).

    Существующие записи НЕ перезаписываются: история должна оставаться
    последовательной (каждый снимок отражает elo на момент завершения
    турнира). Для турниров, завершённых раньше появления этой функции,
    недостающие снимки создаются при старте приложения с текущими
    значениями.

    Возвращает число созданных записей. Коммитит в конце."""
    if competition.status != "completed":
        return 0

    participants = (
        db.query(CompetitionParticipant)
        .filter(CompetitionParticipant.competition_id == competition.id)
        .all()
    )
    athlete_ids = {p.athlete_id for p in participants}
    if not athlete_ids:
        return 0

    stats_rows = {
        s.athlete_id: s
        for s in db.query(AthleteStatistic)
        .filter(AthleteStatistic.athlete_id.in_(athlete_ids))
        .all()
    }
    existing = {
        (h.athlete_id, h.competition_id, h.hand)
        for h in db.query(EloHistory)
        .filter(EloHistory.competition_id == competition.id)
        .all()
    }

    created = 0
    for aid in athlete_ids:
        stats = stats_rows.get(aid)
        if stats is None:
            continue
        values = {
            "left": stats.elo_left,
            "right": stats.elo_right,
            "both": elo_combined(stats.elo_left, stats.elo_right),
        }
        for hand, elo in values.items():
            if (aid, competition.id, hand) in existing:
                continue
            db.add(
                EloHistory(
                    athlete_id=aid,
                    competition_id=competition.id,
                    hand=hand,
                    elo=elo,
                )
            )
            created += 1
    db.commit()
    return created


def recompute_match_participants(db: Session, match: Match) -> None:
    """Пересчитывает статистику двух участников конкретного матча —
    вызывается после каждого apply_match_result, тем же местом, что и
    сам Эло (см. app/api/v1/sync/matches.py)."""
    for pid in (match.p1_id, match.p2_id):
        if pid is None:
            continue
        participant = db.get(CompetitionParticipant, pid)
        if participant is not None:
            recompute_athlete_statistics(db, participant.athlete_id)


def recompute_category_athletes(db: Session, category_id: int, hand: str) -> None:
    """Пересчитывает статистику ВСЕХ участников категории+руки — нужно
    после results_engine.finalize_category_results, потому что финал
    может изменить медаль сразу нескольким людям (например, 3-е место
    в нижней сетке), а не только двум игрокам последнего матча."""
    matches = (
        db.query(Match)
        .filter(Match.category_id == category_id, Match.hand == hand)
        .all()
    )
    participant_ids = set()
    for m in matches:
        if m.p1_id:
            participant_ids.add(m.p1_id)
        if m.p2_id:
            participant_ids.add(m.p2_id)
    if not participant_ids:
        return

    athlete_ids = {
        athlete_id
        for (athlete_id,) in db.query(CompetitionParticipant.athlete_id)
        .filter(CompetitionParticipant.id.in_(participant_ids))
        .all()
    }
    for athlete_id in athlete_ids:
        recompute_athlete_statistics(db, athlete_id)
