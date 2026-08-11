from app.db.models.matches import Match
from app.db.models.results import Result
from app.services.results_engine import finalize_category_results

from .factories import make_category, make_competition, make_participant


def _add_match(db, comp, cat, hand, bracket, stage, p1, p2, winner=None, status="pending"):
    m = Match(
        competition_id=comp.id, category_id=cat.id, hand=hand, bracket=bracket,
        stage=stage, p1_id=p1.id if p1 else None, p2_id=p2.id if p2 else None,
        winner_id=winner.id if winner else None, status=status,
    )
    db.add(m)
    db.flush()
    return m


def test_no_results_written_before_final_is_played(db_session):
    comp = make_competition(db_session)
    cat = make_category(db_session, comp)
    a = make_participant(db_session, comp, cat, "A")
    b = make_participant(db_session, comp, cat, "B")
    _add_match(db_session, comp, cat, "Правая", "winners", 0, a, b, status="pending")

    changed = finalize_category_results(db_session, cat.id, "Правая")

    assert changed is False
    assert db_session.query(Result).count() == 0


def test_single_elimination_final_gives_gold_and_silver(db_session):
    comp = make_competition(db_session)
    cat = make_category(db_session, comp)
    a = make_participant(db_session, comp, cat, "A")
    b = make_participant(db_session, comp, cat, "B")
    _add_match(db_session, comp, cat, "Правая", "winners", 0, a, b, winner=a, status="done")

    changed = finalize_category_results(db_session, cat.id, "Правая")
    db_session.flush()

    assert changed is True
    results = {r.competition_participant_id: (r.place, r.medal) for r in db_session.query(Result)}
    assert results[a.id] == (1, "gold")
    assert results[b.id] == (2, "silver")


def test_single_elimination_semifinal_losers_share_bronze(db_session):
    comp = make_competition(db_session)
    cat = make_category(db_session, comp)
    a = make_participant(db_session, comp, cat, "A")
    b = make_participant(db_session, comp, cat, "B")
    c = make_participant(db_session, comp, cat, "C")
    d = make_participant(db_session, comp, cat, "D")

    # полуфинал (stage 0): a побеждает b, c побеждает d
    _add_match(db_session, comp, cat, "Правая", "winners", 0, a, b, winner=a, status="done")
    _add_match(db_session, comp, cat, "Правая", "winners", 0, c, d, winner=c, status="done")
    # финал (stage 1)
    _add_match(db_session, comp, cat, "Правая", "winners", 1, a, c, winner=a, status="done")

    finalize_category_results(db_session, cat.id, "Правая")
    db_session.flush()

    results = {r.competition_participant_id: (r.place, r.medal) for r in db_session.query(Result)}
    assert results[a.id] == (1, "gold")
    assert results[c.id] == (2, "silver")
    assert results[b.id] == (3, "bronze")
    assert results[d.id] == (3, "bronze")


def test_double_elimination_grand_final_and_lb_bronze(db_session):
    comp = make_competition(db_session)
    cat = make_category(db_session, comp)
    a = make_participant(db_session, comp, cat, "A")  # WB champion
    b = make_participant(db_session, comp, cat, "B")  # LB champion (2nd finalist)
    c = make_participant(db_session, comp, cat, "C")  # проиграл LB финал -> бронза

    _add_match(db_session, comp, cat, "Правая", "losers", 3, b, c, winner=b, status="done")
    _add_match(db_session, comp, cat, "Правая", "final", 4, a, b, winner=a, status="done")

    finalize_category_results(db_session, cat.id, "Правая")
    db_session.flush()

    results = {r.competition_participant_id: (r.place, r.medal) for r in db_session.query(Result)}
    assert results[a.id] == (1, "gold")
    assert results[b.id] == (2, "silver")
    assert results[c.id] == (3, "bronze")


def test_grand_final_replay_overrides_first_grand_final(db_session):
    """Если WB-чемпион проигрывает гранд-финал, требуется переигровка —
    и именно её исход должен определять итоговое золото/серебро."""
    comp = make_competition(db_session)
    cat = make_category(db_session, comp)
    a = make_participant(db_session, comp, cat, "A")  # WB champion
    b = make_participant(db_session, comp, cat, "B")  # LB champion

    _add_match(db_session, comp, cat, "Правая", "final", 4, a, b, winner=b, status="done")
    _add_match(db_session, comp, cat, "Правая", "final", 5, a, b, winner=b, status="done")

    finalize_category_results(db_session, cat.id, "Правая")
    db_session.flush()

    results = {r.competition_participant_id: (r.place, r.medal) for r in db_session.query(Result)}
    assert results[b.id] == (1, "gold")
    assert results[a.id] == (2, "silver")


def test_recompute_is_idempotent_and_self_corrects(db_session):
    comp = make_competition(db_session)
    cat = make_category(db_session, comp)
    a = make_participant(db_session, comp, cat, "A")
    b = make_participant(db_session, comp, cat, "B")
    m = _add_match(db_session, comp, cat, "Правая", "winners", 0, a, b, winner=a, status="done")

    finalize_category_results(db_session, cat.id, "Правая")
    finalize_category_results(db_session, cat.id, "Правая")
    assert db_session.query(Result).count() == 2  # не задвоилось

    # организатор исправил победителя задним числом
    m.winner_id = b.id
    finalize_category_results(db_session, cat.id, "Правая")
    db_session.flush()

    results = {r.competition_participant_id: r.place for r in db_session.query(Result)}
    assert results[b.id] == 1
    assert results[a.id] == 2
