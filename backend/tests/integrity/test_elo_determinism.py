"""Эло-движок: детерминированные дельты. Повторный apply_match_result того
же результата (ретрай PATCH после потерянного ответа) должен давать чистый
ноль — раньше random.randint выдавал новые дельты и рейтинг «дрейфовал».

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
from app.db.models.competitions import Competition, CompetitionParticipant
from app.db.models.matches import Match
from app.db.models.statistics import AthleteStatistic
from app.services.elo_engine import _calculate_deltas, apply_match_result


def _make_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class EloDeterminismTest(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        comp = Competition(name="Т", date=date(2026, 1, 1), status="in_progress")
        self.db.add(comp)
        self.db.flush()
        cat = Category(competition_id=comp.id, name="80 кг", hand="Правая")
        self.db.add(cat)
        self.db.flush()
        self.comp, self.cat = comp, cat
        self.p1 = self._part("А", 1000)
        self.p2 = self._part("Б", 1000)
        self.db.commit()

    def _part(self, name, elo):
        athlete = Athlete(full_name=name)
        self.db.add(athlete)
        self.db.flush()
        self.db.add(
            AthleteStatistic(athlete_id=athlete.id, elo_left=elo, elo_right=elo)
        )
        p = CompetitionParticipant(
            competition_id=self.comp.id, category_id=self.cat.id, athlete_id=athlete.id
        )
        self.db.add(p)
        self.db.flush()
        return p

    def _match(self, winner):
        m = Match(
            competition_id=self.comp.id,
            category_id=self.cat.id,
            hand="Левая",
            status="done",
            p1_id=self.p1.id,
            p2_id=self.p2.id,
            winner_id=winner.id,
        )
        self.db.add(m)
        self.db.flush()
        return m

    def _elo(self, participant):
        return self.db.get(
            AthleteStatistic, participant.athlete_id
        ).elo_left

    def test_replay_same_result_is_net_zero(self):
        match = self._match(self.p1)
        apply_match_result(self.db, match)
        self.db.flush()
        after_first = (self._elo(self.p1), self._elo(self.p2))

        # Повтор того же результата: откат старых дельт + детерминированный
        # пересчёт = ровно то же состояние, дрейфа нет.
        apply_match_result(self.db, match)
        self.db.flush()
        self.assertEqual((self._elo(self.p1), self._elo(self.p2)), after_first)

        # И третий раз — тоже ноль.
        apply_match_result(self.db, match)
        self.db.flush()
        self.assertEqual((self._elo(self.p1), self._elo(self.p2)), after_first)

    def test_winner_correction_applies_once(self):
        match = self._match(self.p1)
        apply_match_result(self.db, match)
        self.db.flush()
        a_won = (self._elo(self.p1), self._elo(self.p2))

        # Исправление результата: победил p2. Старый результат откатывается,
        # начисляется ровно один новый.
        match.winner_id = self.p2.id
        apply_match_result(self.db, match)
        self.db.flush()
        b_won = (self._elo(self.p1), self._elo(self.p2))
        self.assertNotEqual(a_won, b_won)

        # Повторное применение исправленного результата — ноль.
        apply_match_result(self.db, match)
        self.db.flush()
        self.assertEqual((self._elo(self.p1), self._elo(self.p2)), b_won)

    def test_deltas_deterministic_for_same_seed(self):
        self.assertEqual(
            _calculate_deltas(1000, 1000, (1, 10, 20, "Правая", 10)),
            _calculate_deltas(1000, 1000, (1, 10, 20, "Правая", 10)),
        )
        # В случайном диапазоне 15-20 есть вариативность — убеждаемся, что
        # сид действительно влияет (иначе тест был бы тавтологией).
        seeds = {(1, 10, 20, "Правая", i) for i in range(5)}
        self.assertGreater(
            len({_calculate_deltas(1200, 1000, s) for s in seeds}), 1
        )

    def tearDown(self):
        self.db.close()


if __name__ == "__main__":
    unittest.main()
