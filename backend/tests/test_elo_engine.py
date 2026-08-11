from app.db.models.matches import Match
from app.db.models.statistics import AthleteStatistic
from app.services.elo_engine import apply_match_result, elo_combined

from .factories import make_category, make_competition, make_participant


def _stats(db, participant):
    return (
        db.query(AthleteStatistic)
        .filter(AthleteStatistic.athlete_id == participant.athlete_id)
        .first()
    )


def test_equal_rating_win_uses_fixed_delta(db_session):
    """При разнице рейтинга <=99 дельта детерминирована: +10 победителю,
    -15 проигравшему (см. elo_engine._calculate_deltas, ветка diff<=99 —
    единственная без random.randint, поэтому пригодна для точного теста)."""
    comp = make_competition(db_session)
    cat = make_category(db_session, comp, hand="Правая")
    p1 = make_participant(db_session, comp, cat, "Иван Иванов", elo_right=1000)
    p2 = make_participant(db_session, comp, cat, "Пётр Петров", elo_right=1000)

    match = Match(
        competition_id=comp.id, category_id=cat.id, hand="Правая",
        bracket="winners", p1_id=p1.id, p2_id=p2.id, winner_id=p1.id, status="done",
    )
    db_session.add(match)
    db_session.flush()

    apply_match_result(db_session, match)

    assert _stats(db_session, p1).elo_right == 1010
    assert _stats(db_session, p2).elo_right == 985
    assert match.elo_applied is True
    assert match.elo_delta_p1 == 10
    assert match.elo_delta_p2 == -15


def test_bye_match_is_ignored(db_session):
    comp = make_competition(db_session)
    cat = make_category(db_session, comp, hand="Левая")
    p1 = make_participant(db_session, comp, cat, "Иван Иванов")

    match = Match(
        competition_id=comp.id, category_id=cat.id, hand="Левая",
        bracket="winners", p1_id=p1.id, p2_id=None, winner_id=p1.id,
        is_bye=True, status="done",
    )
    db_session.add(match)
    db_session.flush()

    apply_match_result(db_session, match)

    assert _stats(db_session, p1).elo_left == 1000
    assert match.elo_applied is False


def test_manual_override_blocks_recalculation(db_session):
    comp = make_competition(db_session)
    cat = make_category(db_session, comp, hand="Правая")
    p1 = make_participant(db_session, comp, cat, "Иван Иванов")
    p2 = make_participant(db_session, comp, cat, "Пётр Петров")
    _stats(db_session, p1).is_manual_override = True
    db_session.flush()

    match = Match(
        competition_id=comp.id, category_id=cat.id, hand="Правая",
        bracket="winners", p1_id=p1.id, p2_id=p2.id, winner_id=p2.id, status="done",
    )
    db_session.add(match)
    db_session.flush()

    apply_match_result(db_session, match)

    assert match.elo_applied is False
    assert _stats(db_session, p1).elo_right == 1000
    assert _stats(db_session, p2).elo_right == 1000


def test_correction_rolls_back_previous_delta_before_reapplying(db_session):
    """Если winner_id матча меняется повторным PATCH (десктоп прислал
    исправление), старая дельта должна откатиться, а не задвоиться."""
    comp = make_competition(db_session)
    cat = make_category(db_session, comp, hand="Правая")
    p1 = make_participant(db_session, comp, cat, "Иван Иванов")
    p2 = make_participant(db_session, comp, cat, "Пётр Петров")

    match = Match(
        competition_id=comp.id, category_id=cat.id, hand="Правая",
        bracket="winners", p1_id=p1.id, p2_id=p2.id, winner_id=p1.id, status="done",
    )
    db_session.add(match)
    db_session.flush()
    apply_match_result(db_session, match)
    assert _stats(db_session, p1).elo_right == 1010

    # организатор исправил победителя на p2
    match.winner_id = p2.id
    apply_match_result(db_session, match)

    # p1 должен вернуться к 1000, а не остаться на 1010-15
    assert _stats(db_session, p1).elo_right == 985
    assert _stats(db_session, p2).elo_right == 1010


def test_elo_combined_rounds_average():
    assert elo_combined(1000, 1001) == 1001 or elo_combined(1000, 1001) == 1000
    assert elo_combined(1000, 1000) == 1000
