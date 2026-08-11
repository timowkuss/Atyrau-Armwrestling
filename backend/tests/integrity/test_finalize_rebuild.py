"""Повторная финализация турнира (status -> completed ещё раз, или повторный
вызов finalize_competition): ничего не задваивается, а при изменившихся
местах результаты и начисления клубам пересобираются, а не накапливаются.

Запуск: python -m pytest tests/integrity -q
"""

import os

os.environ.setdefault("JWT_SECRET", "test-secret-0123456789abcdef0123456789abcdef")
os.environ.setdefault("DESKTOP_SYNC_TOKEN", "test-sync-token")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import unittest
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
import app.db.models  # noqa: F401
from app.db.models.athletes import Athlete
from app.db.models.categories import Category
from app.db.models.club_rating import ClubRatingHistory
from app.db.models.clubs import Club
from app.db.models.competitions import Competition, CompetitionParticipant
from app.db.models.matches import Match
from app.db.models.results import Result
from app.db.models.statistics import AthleteStatistic
from app.services import club_rating as cr


def _make_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class FinalizeRebuildTest(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.club_a = Club(name="Клуб А")
        self.club_b = Club(name="Клуб Б")
        self.db.add_all([self.club_a, self.club_b])
        self.db.flush()
        self.ath_a = self._ath("Иван Иванов", self.club_a)
        self.ath_b = self._ath("Пётр Петров", self.club_b)
        self.comp = Competition(name="Чемпионат", date=date(2026, 1, 15), status="completed")
        self.db.add(self.comp)
        self.db.flush()
        self.cat = Category(competition_id=self.comp.id, name="80 кг", hand="Обе")
        self.db.add(self.cat)
        self.db.flush()
        self.p1 = self._participant(self.ath_a, "Клуб А")
        self.p2 = self._participant(self.ath_b, "Клуб Б")
        self.db.commit()

    def _ath(self, name, club):
        a = Athlete(full_name=name, club_id=club.id if club else None)
        self.db.add(a)
        self.db.flush()
        self.db.add(AthleteStatistic(athlete_id=a.id))
        return a

    def _participant(self, athlete, club_name):
        p = CompetitionParticipant(
            competition_id=self.comp.id,
            category_id=self.cat.id,
            athlete_id=athlete.id,
            club_at_event=club_name,
        )
        self.db.add(p)
        self.db.flush()
        return p

    def _final(self, winner, loser):
        self.db.add(Match(
            competition_id=self.comp.id, category_id=self.cat.id, hand="Правая",
            bracket="final", status="done", p1_id=winner.id, p2_id=loser.id,
            winner_id=winner.id,
        ))
        self.db.flush()

    def _result_place(self, participant):
        r = (
            self.db.query(Result)
            .filter(Result.competition_participant_id == participant.id)
            .first()
        )
        return r.place if r else None

    def _place_history_count(self):
        return (
            self.db.query(ClubRatingHistory)
            .filter(
                ClubRatingHistory.tournament_id == self.comp.id,
                ClubRatingHistory.reason == cr.REASON_PLACE,
            )
            .count()
        )

    def test_double_finalize_no_double_points(self):
        self._final(self.p1, self.p2)
        self.db.commit()

        cr.finalize_competition(self.db, self.comp)
        cr.finalize_competition(self.db, self.comp)
        cr.finalize_competition(self.db, self.comp)

        # А: 1 место 10 + участие 5 = 15; Б: 2 место 6 + участие 5 = 11
        self.assertEqual(cr.get_club_rating(self.db, self.club_a.id), 15)
        self.assertEqual(cr.get_club_rating(self.db, self.club_b.id), 11)
        # Места/история без дублей
        self.assertEqual(self._result_place(self.p1), 1)
        self.assertEqual(self._result_place(self.p2), 2)
        self.assertEqual(self._place_history_count(), 2)

    def test_changed_result_rebuilds_places_and_points(self):
        self._final(self.p1, self.p2)
        self.db.commit()
        cr.finalize_competition(self.db, self.comp)
        self.assertEqual(cr.get_club_rating(self.db, self.club_a.id), 15)
        self.assertEqual(cr.get_club_rating(self.db, self.club_b.id), 11)

        # Исправление результата задним числом: победил p2.
        final = (
            self.db.query(Match)
            .filter(Match.competition_id == self.comp.id)
            .first()
        )
        final.winner_id = self.p2.id
        self.db.commit()
        cr.finalize_competition(self.db, self.comp)

        # Места пересобрались
        self.assertEqual(self._result_place(self.p1), 2)
        self.assertEqual(self._result_place(self.p2), 1)
        # Начисления клубов тоже: у А осталось участие (+5) + 2 место (+6) = 11,
        # у Б — 1 место (10) + участие (5) = 15 (старые +10/+6 сняты).
        self.assertEqual(cr.get_club_rating(self.db, self.club_a.id), 11)
        self.assertEqual(cr.get_club_rating(self.db, self.club_b.id), 15)
        # В истории по-прежнему ровно по одной записи PLACE на клуб
        self.assertEqual(self._place_history_count(), 2)
        history = cr.get_club_rating_history(self.db, self.club_b.id)
        place_rows = [h for h in history if h.reason == cr.REASON_PLACE]
        self.assertEqual(len(place_rows), 1)
        self.assertEqual(place_rows[0].points, 10)

    def tearDown(self):
        self.db.close()


if __name__ == "__main__":
    unittest.main()
