from datetime import date

from app.db.models.athletes import Athlete
from app.db.models.competitions import Competition, CompetitionParticipant
from app.db.models.categories import Category
from app.db.models.statistics import AthleteStatistic


def make_competition(db, name="Тестовый турнир"):
    comp = Competition(name=name, date=date(2026, 1, 1), status="in_progress")
    db.add(comp)
    db.flush()
    return comp


def make_category(db, competition, hand="Правая", name="До 80 кг"):
    cat = Category(competition_id=competition.id, hand=hand, name=name)
    db.add(cat)
    db.flush()
    return cat


def make_participant(db, competition, category, full_name, elo_left=1000, elo_right=1000):
    athlete = Athlete(full_name=full_name)
    db.add(athlete)
    db.flush()
    db.add(AthleteStatistic(athlete_id=athlete.id, elo_left=elo_left, elo_right=elo_right))
    participant = CompetitionParticipant(
        competition_id=competition.id, athlete_id=athlete.id, category_id=category.id
    )
    db.add(participant)
    db.flush()
    return participant
