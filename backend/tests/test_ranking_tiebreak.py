"""Сортировка рейтингов спортсменов, тренеров и клубов.

Запуск:  backend/venv/Scripts/python -m unittest tests.test_ranking_tiebreak -v

Проверяет правила порядка мест при равных значениях (см. ranking_compare.py):
  - спортсмены: рейтинг → медальные очки (🥇=6, 🥈=3, 🥉=2) → винрейт;
  - тренеры: рейтинг → медальные очки учеников → активные ученики;
  - клубы: рейтинг → медальные очки спортсменов клуба → активные спортсмены;
  - полное совпадение → одинаковое место (1, 2, 2, 4, ...).
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
from app.db.models.rankings import AthleteRanking
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
                 elo_left=1000, elo_right=1000, club_id=None, coach_id=None,
                 is_hidden=False, club_active=False):
        a = Athlete(
            full_name=full_name, gender=gender,
            club_id=club_id, coach_id=coach_id,
            is_hidden=is_hidden, club_active=club_active,
        )
        self.db.add(a)
        self.db.flush()
        self.db.add(AthleteStatistic(
            athlete_id=a.id, win_rate=win_rate,
            gold_count=gold, silver_count=silver, bronze_count=bronze,
            elo_left=elo_left, elo_right=elo_right,
        ))
        return a

    def _club(self, name, rating_points=0):
        c = Club(name=name, rating_points=rating_points)
        self.db.add(c)
        self.db.flush()
        return c

    def _coach(self, full_name):
        c = Coach(full_name=full_name, is_hidden=False)
        self.db.add(c)
        self.db.flush()
        return c

    # ── спортсмены (AthleteRanking) ────────────────────────────
    def test_athlete_tiebreak_medal_points_then_winrate_then_shared_position(self):
        # Спортсмен Б: 2🥇 + 0🥈 + 10🥉 = 32 очка > Спортсмен А: 1🥇 + 3🥈 + 5🥉 = 25.
        a = self._athlete("А", win_rate=0.8, gold=1, silver=3, bronze=5)
        b = self._athlete("Б", win_rate=0.5, gold=2, silver=0, bronze=10)
        c = self._athlete("В", win_rate=0.9, gold=1, silver=3, bronze=5)
        d = self._athlete("Г", win_rate=0.9, gold=1, silver=3, bronze=5)
        for athlete in (a, b, c, d):
            self.db.add(AthleteRanking(
                athlete_id=athlete.id, points=1000, scope_gender="male", period="all-time",
            ))
        self.db.commit()

        rows = athlete_rankings(period="all-time", gender="male", limit=100, db=self.db)
        order = [r.athlete_name for r in rows]
        # Б выше по медальным очкам; В/Г делят медали, у В выше винрейт чем у А;
        # В и Г полностью равны → одинаковое место (2 и 2).
        self.assertEqual(order, ["Б", "В", "Г", "А"])
        self.assertEqual([r.position for r in rows], [1, 2, 2, 4])

    # ── клубы ──────────────────────────────────────────────────
    def test_club_tiebreak_medal_points_then_active_then_shared_position(self):
        x = self._club("Икс", rating_points=1000)
        y = self._club("Игрек", rating_points=1000)
        z = self._club("Зет", rating_points=1000)
        q = self._club("Ку", rating_points=1000)
        # Икс: 1🥇 = 6 очков, 1 активный
        self._athlete("С1", club_id=x.id, gold=1, club_active=True)
        # Игрек: 1🥈 = 3 очка → ниже Икс по медальным очкам
        self._athlete("С2", club_id=y.id, silver=1, club_active=True)
        # Зет: 1🥇 = 6 очков, 2 активных → выше Икс по числу активных
        self._athlete("С3", club_id=z.id, gold=1, club_active=True)
        self._athlete("С4", club_id=z.id, club_active=True)
        # Ку: 1🥇 = 6 очков, 1 активный → полный твин Икс → общее место
        self._athlete("С5", club_id=q.id, gold=1, club_active=True)
        self.db.commit()

        rows = club_rankings(limit=100, db=self.db)
        by_name = {r.club_name: r for r in rows}
        # Зет и Икс делят медальные очки (6), активных: Зет 2 > Икс 1.
        self.assertEqual(rows[0].club_name, "Зет")
        self.assertEqual(rows[1].club_name, "Икс")
        self.assertEqual(rows[2].club_name, "Ку")
        self.assertEqual(rows[3].club_name, "Игрек")
        # Икс и Ку полностью равны → одинаковое место.
        self.assertEqual(by_name["Икс"].position, by_name["Ку"].position)
        self.assertEqual(by_name["Зет"].position, 1)
        self.assertEqual(by_name["Икс"].position, 2)
        self.assertEqual(by_name["Игрек"].position, 4)

    # ── тренеры ────────────────────────────────────────────────
    def test_coach_tiebreak_student_medals_then_active_then_shared_position(self):
        big = self._coach("Много очков учеников")
        many_active = self._coach("Больше активных")
        twin_a = self._coach("Твин-А")
        twin_b = self._coach("Твин-Б")
        # big: 2🥇 учениками = 12 очков
        self._athlete("У1", coach_id=big.id, gold=1)
        self._athlete("У2", coach_id=big.id, gold=1)
        # many_active: 1🥇 = 6 очков, но 2 активных ученика
        self._athlete("У3", coach_id=many_active.id, gold=1)
        self._athlete("У4", coach_id=many_active.id)
        # twin_a / twin_b: по 1🥇 = 6 очков, 1 активный → полный твин
        self._athlete("У5", coach_id=twin_a.id, gold=1)
        self._athlete("У6", coach_id=twin_b.id, gold=1)
        self.db.commit()

        rows = coach_rankings(limit=100, db=self.db)
        order = [r.coach_name for r in rows]
        # big выше по медальным очкам (12 > 6); many_active выше твинов по числу
        # активных (2 > 1); твины полностью равны → одинаковое место.
        self.assertEqual(order, ["Много очков учеников", "Больше активных", "Твин-А", "Твин-Б"])
        self.assertEqual([r.position for r in rows], [1, 2, 3, 3])

    # ── ELO (отображаемый рейтинг спортсменов) ─────────────────
    def test_elo_tiebreak_medal_points_then_winrate_then_shared_position(self):
        # Одинаковое Эло (правая 1400): решает медальные очки, затем винрейт.
        m = self._athlete("Медали", elo_right=1400, elo_left=1300, gold=2, win_rate=0.3)
        w = self._athlete("Винрейт", elo_right=1400, elo_left=1300, gold=1, win_rate=0.9)
        t1 = self._athlete("Твин-1", elo_right=1400, elo_left=1300, gold=1, win_rate=0.7)
        t2 = self._athlete("Твин-2", elo_right=1400, elo_left=1300, gold=1, win_rate=0.7)
        self.db.commit()

        rows = elo_rankings(hand="right", limit=100, db=self.db)
        order = [r.athlete_name for r in rows]
        # Медали: 12 > 6 → Медали выше; Винрейт (0.9) выше Твинов (0.7); твины равны.
        self.assertEqual(order, ["Медали", "Винрейт", "Твин-1", "Твин-2"])
        self.assertEqual([r.position for r in rows], [1, 2, 3, 3])


if __name__ == "__main__":
    unittest.main()
