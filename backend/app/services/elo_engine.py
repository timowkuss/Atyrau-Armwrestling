"""Рейтинг Эло по руке для армрестлинга.

Логика, как договаривались: у каждого спортсмена два независимых
рейтинга — elo_left и elo_right (хранятся в AthleteStatistic). Общий
рейтинг, который видно на сайте одной цифрой, нигде не хранится и
считается на лету как (elo_left + elo_right) / 2 — см.
app/schemas/athletes.py: AthleteStatisticsOut.elo_combined.

Обновление происходит в момент, когда десктоп присылает winner_id матча
через PATCH /sync/matches/{id} (app/api/v1/sync/matches.py), т.е. в
реальном времени по ходу турнира, а не пакетом после публикации —
тем же способом, что и остальная синхронизация (см. ARCHITECTURE.md §5).

Идемпотентность: у матча есть elo_applied/elo_delta_p1/elo_delta_p2.
Если десктоп присылает исправленного победителя повторным PATCH
(бывает — см. историю правок стадии офлайн-очереди), сначала откатывается
старая дельта, потом считается и применяется новая. Один и тот же
результат не проведёт по рейтингу дважды.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models.competitions import CompetitionParticipant
from app.db.models.matches import Match
from app.db.models.statistics import AthleteStatistic

K_FACTOR = 32
DEFAULT_ELO = 1000


def _hand_field(hand: str) -> str | None:
    """'Левая' -> 'elo_left', 'Правая' -> 'elo_right'. Категории/матчи
    двоеборья создают отдельный матч на каждую руку (см.
    app/db/models/matches.py), так что на уровне матча рука всегда
    конкретна — 'Обе' сюда не долетает; если долетело что-то незнакомое,
    считаем это ошибкой данных и пропускаем пересчёт, а не гадаем."""
    normalized = (hand or "").strip().lower()
    if normalized.startswith("лев"):
        return "elo_left"
    if normalized.startswith("прав"):
        return "elo_right"
    return None


def _expected_score(rating_a: int, rating_b: int) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def _get_or_create_stats(db: Session, athlete_id: int) -> AthleteStatistic:
    stats = (
        db.query(AthleteStatistic)
        .filter(AthleteStatistic.athlete_id == athlete_id)
        .first()
    )
    if stats is None:
        # На практике строка создаётся сразу при создании атлета (см.
        # sync/athletes.py, admin/athletes.py), это подстраховка на случай
        # более старых записей, заведённых до появления AthleteStatistic.
        stats = AthleteStatistic(athlete_id=athlete_id)
        db.add(stats)
        db.flush()
    return stats


def apply_match_result(db: Session, match: Match) -> None:
    """Пересчитывает Эло по итогам матча. Вызывается из
    sync/matches.py после того, как в матче появился winner_id.
    Ничего не коммитит — коммит делает вызывающий код."""

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

    # Рейтинг, зафиксированный админом вручную (через
    # PATCH /admin/athletes/{id}/statistics), не трогаем автоматическим
    # пересчётом ни для кого из пары — иначе один зафиксированный и один
    # живой рейтинг разъедутся и Эло перестанет быть игрой с нулевой
    # суммой (см. is_manual_override, тот же принцип, что и для
    # win/loss статистики).
    if stats1.is_manual_override or stats2.is_manual_override:
        return

    # Если этот матч уже когда-то учитывался (пришло исправление
    # winner_id) — сначала откатываем прошлую дельту.
    if match.elo_applied:
        if match.elo_delta_p1:
            setattr(stats1, field, getattr(stats1, field) - match.elo_delta_p1)
        if match.elo_delta_p2:
            setattr(stats2, field, getattr(stats2, field) - match.elo_delta_p2)

    rating1 = getattr(stats1, field)
    rating2 = getattr(stats2, field)

    score1 = 1.0 if match.winner_id == p1.id else 0.0
    score2 = 1.0 - score1

    expected1 = _expected_score(rating1, rating2)
    expected2 = 1.0 - expected1

    delta1 = round(K_FACTOR * (score1 - expected1))
    delta2 = round(K_FACTOR * (score2 - expected2))

    setattr(stats1, field, rating1 + delta1)
    setattr(stats2, field, rating2 + delta2)

    match.elo_delta_p1 = delta1
    match.elo_delta_p2 = delta2
    match.elo_applied = True


def elo_combined(elo_left: int, elo_right: int) -> int:
    """Общий рейтинг для сайта: среднее по двум рукам, как договаривались."""
    return round((elo_left + elo_right) / 2)
