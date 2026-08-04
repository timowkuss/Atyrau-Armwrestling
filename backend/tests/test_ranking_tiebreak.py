"""Тай-брейки в рейтингах при равных очках.

Запуск:  backend/venv/Scripts/python -m unittest tests.test_ranking_tiebreak -v

При равных очках порядок определяется детерминированно:
  - спортсмены: win_rate → золото → серебро → бронза → id;
  - клубы: золото → серебро → бронза → id;
  - тренеры: число учеников → id;
  - ELO: по второй руке → win_rate → id.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DESKTOP_SYNC_TOKEN", "test-sync-token")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
import app.db.models  # noqa: F401  (регистрирует все модели в Base.metadata)
from app.db.models.athletes import Athlete
from app.db.models.clubs import Club
from app.db.models.coaches import Coach
from app.db.models.rankings import AthleteRanking, ClubRanking
from app.db.models.statistics import AthleteStatistic
from app.api.v1.public.rankings import (
    athlete_rankings,
    club_rankings,
    coach_rankings,
    elo_rankings,
)


class RankingTiebreakTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self._engine = engine
        self.db = sessionmaker(bind=engine, autoflush=False)()

    def tearDown(self):
        self.db.close()
        self._engine.dispose()

    def _athlete(self, full_name, gender="male", win_rate=0.0, gold=0, silver=0, bronze=0,
                 elo_left=1000, elo_right=1000):
        a = Athlete(full_name=full_name, gender=gender)
        self.db.add(a)
        self.db.flush()
        self.db.add(AthleteStatistic(
            athlete_id=a.id, win_rate=win_rate,
            gold_count=gold, silver_count=silver, bronze_count=bronze,
            elo_left=elo_left, elo_right=elo_right,
        ))
        return a

    def _club(self, name):
        c = Club(name=name)
        self.db.add(c)
        self.db.flush()
        return c

    def _coach(self, full_name):
        c = Coach(full_name=full_name, is_hidden=False)
        self.db.add(c)
        self.db.flush()
        return c

    # ── спортсмены ─────────────────────────────────────────────
    def test_athlete_tiebreak_winrate_then_medals_then_id(self):
        a = self._athlete("А", win_rate=0.8, gold=2, silver=1, bronze=0)
        b = self._athlete("Б", win_rate=0.8, gold=2, silver=0, bronze=3)
        c = self._athlete("В", win_rate=0.6, gold=5, silver=0, bronze=0)
        d = self._athlete("Г", win_rate=0.8, gold=2, silver=1, bronze=0)
        for athlete in (a, b, c, d):
            self.db.add(AthleteRanking(
                athlete_id=athlete.id, points=1000, scope_gender="male", period="all-time",
            ))
        self.db.commit()

        rows = athlete_rankings(period="all-time", gender="male", limit=100, db=self.db)
        order = [r.athlete_name for r in rows]
        # В/Г делят win_rate/медали → выше тот, кто раньше добавлен (id меньше)
        self.assertEqual(order, ["А", "Г", "Б", "В"])
        self.assertEqual([r.position for r in rows], [1, 2, 3, 4])

    # ── клубы ──────────────────────────────────────────────────
    def test_club_tiebreak_medals_then_id(self):
        x = self._club("Икс")
        y = self._club("Игрек")
        z = self._club("Зет")
        self.db.add(ClubRanking(club_id=x.id, points=1000, gold_count=3, silver_count=0, bronze_count=0))
        self.db.add(ClubRanking(club_id=y.id, points=1000, gold_count=3, silver_count=1, bronze_count=0))
        self.db.add(ClubRanking(club_id=z.id, points=1000, gold_count=3, silver_count=1, bronze_count=0))
        self.db.commit()

        rows = club_rankings(limit=100, db=self.db)
        order = [r.club_name for r in rows]
        # Игрек и Зет делят всё → выше тот, кто раньше добавлен
        self.assertEqual(order, ["Игрек", "Зет", "Икс"])
        self.assertEqual([r.position for r in rows], [1, 2, 3])

    # ── тренеры ────────────────────────────────────────────────
    def test_coach_tiebreak_students_then_id(self):
        big = self._coach("Много учеников")
        small = self._coach("Мало учеников")
        for i in range(3):
            a = self._athlete(f"Ученик {i}")
            a.coach_id = big.id
        self.db.flush()
        self.db.commit()

        rows = coach_rankings(limit=100, db=self.db)
        # без учеников rating=1000 у обоих; решает число учеников (3 > 0)
        self.assertEqual(rows[0].coach_name, "Много учеников")
        self.assertEqual(rows[1].coach_name, "Мало учеников")
        self.assertEqual([r.position for r in rows], [1, 2])

    # ── ELO ────────────────────────────────────────────────────
    def test_elo_tiebreak_second_hand_then_winrate_then_id(self):
        # правая рука одинаковая → решает левая, затем win_rate, затем id
        h1 = self._athlete("Руки-1", elo_right=1400, elo_left=1300, win_rate=0.9)
        h2 = self._athlete("Руки-2", elo_right=1400, elo_left=1350, win_rate=0.5)
        h3 = self._athlete("Руки-3", elo_right=1400, elo_left=1350, win_rate=0.7)
        # полный твин (одинаковые эло и win_rate) → выше тот, кто раньше добавлен
        x = self._athlete("Твин-1", elo_right=1200, elo_left=1200, win_rate=0.5)
        y = self._athlete("Твин-2", elo_right=1200, elo_left=1200, win_rate=0.5)
        self.db.commit()

        rows = elo_rankings(hand="right", limit=100, db=self.db)
        order = [r.athlete_name for r in rows]
        self.assertEqual(order, ["Руки-3", "Руки-2", "Руки-1", "Твин-1", "Твин-2"])

        rows_all = elo_rankings(limit=100, db=self.db)
        self.assertEqual([r.athlete_name for r in rows_all],
                         ["Руки-3", "Руки-2", "Руки-1", "Твин-1", "Твин-2"])
        self.assertEqual([r.position for r in rows_all], [1, 2, 3, 4, 5])


if __name__ == "__main__":
    unittest.main()
