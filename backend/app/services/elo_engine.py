from __future__ import annotations

import random

from sqlalchemy.orm import Session

from app.db.models.competitions import CompetitionParticipant
from app.db.models.matches import Match
from app.db.models.statistics import AthleteStatistic

DEFAULT_ELO = 1000
MAX_DELTA = 40

HIGH_RATING_COEFFS = [
    (1400, 1.00),
    (1600, 1.05),
    (1800, 1.10),
    (2000, 1.20),
    (2200, 1.35),
    (float("inf"), 1.50),
]


def _hand_field(hand: str) -> str | None:
    normalized = (hand or "").strip().lower()
    if normalized.startswith("лев"):
        return "elo_left"
    if normalized.startswith("прав"):
        return "elo_right"
    return None


def _high_rating_coeff(rating: int) -> float:
    for threshold, coeff in HIGH_RATING_COEFFS:
        if rating < threshold:
            return coeff
    return 1.50


def _clamp(delta: int) -> int:
    return max(-MAX_DELTA, min(MAX_DELTA, delta))


def _calculate_deltas(
    rating_winner: int, rating_loser: int, rng_seed: tuple
) -> tuple[int, int]:
    """Дельты Эло. Раньше random.randint давал НОВЫЕ случайные значения на
    каждый вызов — повторный apply_match_result того же результата (retry
    PATCH после потерянного ответа) сначала откатывал старые дельты, а
    потом начислял новые, и Эло «дрейфовало» с каждым ретраем. Теперь RNG
    сидируется по (id матча, спортсмены, рука, победитель): повтор того же
    результата даёт ровно те же дельты -> повторный вызов = чистый ноль,
    пересборка истории из матчей детерминирована."""
    rng = random.Random(f"{rng_seed[0]}:{rng_seed[1]}:{rng_seed[2]}:{rng_seed[3]}:{rng_seed[4]}")
    diff = abs(rating_winner - rating_loser)
    higher_won = rating_winner > rating_loser

    if diff <= 99:
        base_gain = 10
        base_loss = -15
    elif diff <= 299:
        if higher_won:
            base_gain = rng.randint(5, 8)
            base_loss = -rng.randint(5, 8)
        else:
            base_gain = rng.randint(15, 20)
            base_loss = -rng.randint(15, 20)
    elif diff <= 499:
        if higher_won:
            base_gain = rng.randint(3, 5)
            base_loss = -rng.randint(3, 5)
        else:
            base_gain = rng.randint(25, 35)
            base_loss = -rng.randint(25, 35)
    else:
        if higher_won:
            base_gain = rng.randint(1, 3)
            base_loss = -rng.randint(1, 3)
        else:
            base_gain = rng.randint(35, 40)
            base_loss = -rng.randint(35, 40)

    return base_gain, base_loss


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


def apply_match_result(db: Session, match: Match) -> None:
    if match.is_bye or match.winner_id is None or match.p1_id is None or match.p2_id is None:
        return

    field = _hand_field(match.hand)
    if field is None:
        return

    p1 = db.get(CompetitionParticipant, match.p1_id)
    p2 = db.get(CompetitionParticipant, match.p2_id)
    if p1 is None or p2 is None:
        return

    stats1 = _get_or_create_stats(db, p1.athlete_id)
    stats2 = _get_or_create_stats(db, p2.athlete_id)

    if stats1.is_manual_override or stats2.is_manual_override:
        return

    if match.elo_applied:
        if match.elo_delta_p1:
            setattr(stats1, field, getattr(stats1, field) - match.elo_delta_p1)
        if match.elo_delta_p2:
            setattr(stats2, field, getattr(stats2, field) - match.elo_delta_p2)

    rating1 = getattr(stats1, field)
    rating2 = getattr(stats2, field)

    if match.winner_id == p1.id:
        winner_stats, loser_stats = stats1, stats2
        winner_rating, loser_rating = rating1, rating2
    else:
        winner_stats, loser_stats = stats2, stats1
        winner_rating, loser_rating = rating2, rating1

    raw_win_delta, raw_loss_delta = _calculate_deltas(
        winner_rating,
        loser_rating,
        (match.id, p1.athlete_id, p2.athlete_id, match.hand, match.winner_id),
    )

    loss_coeff = _high_rating_coeff(loser_rating)
    loser_raw = round(raw_loss_delta * loss_coeff)

    win_delta = _clamp(raw_win_delta)
    loss_delta = _clamp(loser_raw)

    if match.winner_id == p1.id:
        setattr(stats1, field, rating1 + win_delta)
        setattr(stats2, field, rating2 + loss_delta)
        match.elo_delta_p1 = win_delta
        match.elo_delta_p2 = loss_delta
    else:
        setattr(stats1, field, rating1 + loss_delta)
        setattr(stats2, field, rating2 + win_delta)
        match.elo_delta_p1 = loss_delta
        match.elo_delta_p2 = win_delta

    match.elo_applied = True


def elo_combined(elo_left: int, elo_right: int) -> int:
    return round((elo_left + elo_right) / 2)
