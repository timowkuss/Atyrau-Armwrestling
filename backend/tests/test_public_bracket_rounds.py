from datetime import date

from app.api.v1.public.competitions import get_competition_bracket
from app.db.models.athletes import Athlete
from app.db.models.categories import Category
from app.db.models.competitions import Competition, CompetitionParticipant
from app.db.models.matches import Match
from app.db.models.statistics import AthleteStatistic


def _make_participant(db, competition, category, name):
    athlete = Athlete(full_name=name)
    db.add(athlete)
    db.flush()
    db.add(AthleteStatistic(athlete_id=athlete.id, elo_left=1000, elo_right=1000))
    p = CompetitionParticipant(
        competition_id=competition.id, athlete_id=athlete.id, category_id=category.id
    )
    db.add(p)
    db.flush()
    return p


def _match(db, competition, category, bracket, round_name, stage, order, p1=None, p2=None):
    m = Match(
        competition_id=competition.id,
        category_id=category.id,
        hand="Обе",
        bracket=bracket,
        round_name=round_name,
        match_order=order,
        stage=stage,
        p1_id=p1.id if p1 else None,
        p2_id=p2.id if p2 else None,
        status="done" if (p1 and p2) else "pending",
    )
    db.add(m)
    db.flush()
    return m


def test_bracket_preserves_distinct_losers_round_names(db_session):
    """Регрессия: /bracket НЕ должен схлопывать раунды нижней сетки в одно
    имя ('Полуфинал'). Раньше _tablo_round_name() превращала все losers-раунды
    ('LB раунд 1..N') в одно значение, из-за чего фронтенд-компонент
    BracketBoard группировал все матчи нижней сетки в одну колонку без
    соединительных линий. Эндпоинт должен отдавать исходные round_name."""
    comp = Competition(name="Тест", date=date(2026, 1, 1), status="in_progress")
    db_session.add(comp)
    db_session.flush()
    cat = Category(competition_id=comp.id, name="До 80 кг", hand="Обе")
    db_session.add(cat)
    db_session.flush()

    ps = [_make_participant(db_session, comp, cat, f"Спортсмен {i}") for i in range(6)]

    # Нижняя сетка: раунды с разными названиями, как в реальном DE-турнире
    _match(db_session, comp, cat, "losers", "LB раунд 1", stage=2, order=0, p1=ps[0], p2=ps[1])
    _match(db_session, comp, cat, "losers", "LB раунд 2", stage=4, order=0, p1=ps[2], p2=ps[3])
    _match(db_session, comp, cat, "losers", "LB раунд 3", stage=5, order=0, p1=ps[4], p2=ps[5])
    db_session.commit()

    items = get_competition_bracket(comp.id, db_session)

    loser_rounds = [m.round_name for m in items if m.bracket == "losers"]
    assert loser_rounds == ["LB раунд 1", "LB раунд 2", "LB раунд 3"], loser_rounds
    # Ключевое: не должно быть единственного схлопнутого имени
    assert len(set(loser_rounds)) == 3, loser_rounds
    assert "Полуфинал" not in loser_rounds
