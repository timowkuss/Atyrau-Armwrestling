from __future__ import annotations

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.db.models.athletes import Athlete
from app.db.models.competitions import CompetitionParticipant
from app.db.models.results import Result
from app.db.models.statistics import AthleteStatistic

BASE_RATING = 1000
DEFAULT_OLD_ELO = 1000


def _growth_bonus(avg_growth: float) -> int:
    if avg_growth >= 50:
        return 200
    if avg_growth >= 30:
        return 150
    if avg_growth >= 10:
        return 100
    if avg_growth >= 0:
        return 50
    return 0


def _student_coeff(count: int) -> float:
    if count >= 10:
        return 1.0
    if count >= 6:
        return 0.9
    if count >= 3:
        return 0.7
    if count >= 1:
        return 0.5
    return 0.0


def _scale_bonus(count: int) -> int:
    if count >= 11:
        return 50
    if count >= 6:
        return 35
    if count >= 3:
        return 20
    if count >= 1:
        return 10
    return 0


def calculate_coach_rating(
    db: Session,
    coach_id: int,
    old_elo_map: dict[int, int] | None = None,
) -> dict:
    athletes = (
        db.query(Athlete)
        .filter(Athlete.coach_id == coach_id)
        .all()
    )

    if not athletes:
        return {
            "rating": 0,
            "development_score": 0,
            "result_score": 0,
            "scale_score": 0,
            "student_count": 0,
        }

    athlete_ids = [a.id for a in athletes]
    student_count = len(athlete_ids)

    stats_rows = (
        db.query(AthleteStatistic)
        .filter(AthleteStatistic.athlete_id.in_(athlete_ids))
        .all()
    )
    stats_map = {s.athlete_id: s for s in stats_rows}

    total_growth = 0.0
    valid_growth_count = 0

    for aid in athlete_ids:
        s = stats_map.get(aid)
        if s is None:
            continue
        current = round((s.elo_left + s.elo_right) / 2)
        old = (old_elo_map or {}).get(aid, DEFAULT_OLD_ELO)
        growth = current - old
        total_growth += growth
        valid_growth_count += 1

    if valid_growth_count == 0:
        avg_growth = 0.0
    else:
        avg_growth = total_growth / valid_growth_count

    development_bonus = round(_growth_bonus(avg_growth) * _student_coeff(student_count))

    result_points_agg = (
        db.query(
            func.sum(case((Result.place == 1, 10), (Result.place == 2, 6), (Result.place == 3, 3), else_=0)).label("points")
        )
        .join(CompetitionParticipant, Result.competition_participant_id == CompetitionParticipant.id)
        .filter(CompetitionParticipant.athlete_id.in_(athlete_ids))
        .scalar()
    ) or 0

    result_bonus = min(result_points_agg, 100)
    scale = _scale_bonus(student_count)

    final_rating = BASE_RATING + development_bonus + result_bonus + scale

    return {
        "rating": final_rating,
        "development_score": development_bonus,
        "result_score": result_bonus,
        "scale_score": scale,
        "student_count": student_count,
    }
