from app.db.models.matches import Match
from app.db.models.statistics import AthleteStatistic
from app.services.results_engine import finalize_category_results
from app.services.stats_engine import (
    recompute_athlete_statistics,
    recompute_category_athletes,
    recompute_match_participants,
)

from .factories import make_category, make_competition, make_participant


def _stats(db, participant):
    return (
        db.query(AthleteStatistic)
        .filter(AthleteStatistic.athlete_id == participant.athlete_id)
        .first()
    )


def _add_match(db, comp, cat, hand, bracket, stage, p1, p2, winner=None, status="pending"):
    m = Match(
        competition_id=comp.id, category_id=cat.id, hand=hand, bracket=bracket,
        stage=stage, p1_id=p1.id if p1 else None, p2_id=p2.id if p2 else None,
        winner_id=winner.id if winner else None, status=status,
    )
    db.add(m)
    db.flush()
    return m


def test_win_loss_counts_split_by_hand(db_session):
    comp = make_competition(db_session)
    cat = make_category(db_session, comp)
    a = make_participant(db_session, comp, cat, "A")
    b = make_participant(db_session, comp, cat, "B")

    m1 = _add_match(db_session, comp, cat, "Правая", "winners", 0, a, b, winner=a, status="done")
    m2 = _add_match(db_session, comp, cat, "Левая", "winners", 0, a, b, winner=b, status="done")

    recompute_match_participants(db_session, m1)
    recompute_match_participants(db_session, m2)

    sa, sb = _stats(db_session, a), _stats(db_session, b)
    assert (sa.total_wins, sa.total_losses) == (1, 1)
    assert (sa.right_hand_wins, sa.right_hand_losses) == (1, 0)
    assert (sa.left_hand_wins, sa.left_hand_losses) == (0, 1)
    assert (sb.total_wins, sb.total_losses) == (1, 1)
    assert sa.win_rate == 0.5


def test_medal_counts_come_from_results(db_session):
    comp = make_competition(db_session)
    cat = make_category(db_session, comp)
    a = make_participant(db_session, comp, cat, "A")
    b = make_participant(db_session, comp, cat, "B")
    c = make_participant(db_session, comp, cat, "C")
    d = make_participant(db_session, comp, cat, "D")

    _add_match(db_session, comp, cat, "Правая", "winners", 0, a, b, winner=a, status="done")
    _add_match(db_session, comp, cat, "Правая", "winners", 0, c, d, winner=c, status="done")
    _add_match(db_session, comp, cat, "Правая", "winners", 1, a, c, winner=a, status="done")

    changed = finalize_category_results(db_session, cat.id, "Правая")
    assert changed is True
    recompute_category_athletes(db_session, cat.id, "Правая")

    assert _stats(db_session, a).gold_count == 1
    assert _stats(db_session, c).silver_count == 1
    assert _stats(db_session, b).bronze_count == 1
    assert _stats(db_session, d).bronze_count == 1


def test_manual_override_blocks_recompute(db_session):
    comp = make_competition(db_session)
    cat = make_category(db_session, comp)
    a = make_participant(db_session, comp, cat, "A")
    b = make_participant(db_session, comp, cat, "B")
    stats_a = _stats(db_session, a)
    stats_a.is_manual_override = True
    stats_a.total_wins = 999
    db_session.flush()

    m = _add_match(db_session, comp, cat, "Правая", "winners", 0, a, b, winner=a, status="done")
    recompute_match_participants(db_session, m)

    # override-карточка не тронута
    assert _stats(db_session, a).total_wins == 999
    # обычная карточка пересчиталась как положено
    assert _stats(db_session, b).total_losses == 1


def test_recompute_is_from_scratch_and_self_corrects(db_session):
    comp = make_competition(db_session)
    cat = make_category(db_session, comp)
    a = make_participant(db_session, comp, cat, "A")
    b = make_participant(db_session, comp, cat, "B")

    m = _add_match(db_session, comp, cat, "Правая", "winners", 0, a, b, winner=a, status="done")
    recompute_match_participants(db_session, m)
    assert _stats(db_session, a).total_wins == 1

    # организатор исправил победителя задним числом
    m.winner_id = b.id
    recompute_match_participants(db_session, m)

    assert _stats(db_session, a).total_wins == 0
    assert _stats(db_session, a).total_losses == 1
    assert _stats(db_session, b).total_wins == 1
