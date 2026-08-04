"""Сортировка рейтингов спортсменов, тренеров и клубов.

Запуск:  backend/venv/Scripts/python -m unittest tests.test_ranking_tiebreak -v

Проверяет правила порядка мест при равных значениях (см. ranking_compare.py):

  - спортсмены: рейтинг → медальные очки (🥇=6, 🥈=3, 🥉=2) → винрейт →
    победы → дата регистрации → id;
  - тренеры: рейтинг → медальные очки учеников → активные ученики →
    дата регистрации → id;
  - клубы: рейтинг → медальные очки клуба → активные спортсмены →
    дата создания → id.
"""
from __future__ import annotations

import os
import unittest
from datetime import datetime

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

EARLY = datetime(2020, 1, 1)
MIDDLE = datetime(2022, 6, 15)


class RankingTiebreakTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self._engine = engine
        self.db = sessionmaker(bind=engine, autoflush=False)()

    def tearDown(self):
        self.db.close()
        self._engine.dispose()

    def _athlete(self, full_name, gender="male", gold=0, silver=0, bronze=0,
                 wins=0, losses=0, elo_left=1000, elo_right=1000,
                 club_id=None, coach_id=None, is_hidden=False,
                 club_active=False, created_at=None):
        a = Athlete(
            full_name=full_name, gender=gender,
            club_id=club_id, coach_id=coach_id,
            is_hidden=is_hidden, club_active=club_active,
        )
        if created_at is not None:
            a.created_at = created_at
        self.db.add(a)
        self.db.flush()
        self.db.add(AthleteStatistic(
            athlete_id=a.id, total_wins=wins, total_losses=losses,
            gold_count=gold, silver_count=silver, bronze_count=bronze,
            elo_left=elo_left, elo_right=elo_right,
        ))
        return a

    def _club(self, name, rating_points=0, created_at=None):
        c = Club(name=name, rating_points=rating_points)
        if created_at is not None:
            c.created_at = created_at
        self.db.add(c)
        self.db.flush()
        return c

    def _coach(self, full_name, created_at=None):
        c = Coach(full_name=full_name, is_hidden=False)
        if created_at is not None:
            c.created_at = created_at
        self.db.add(c)
        self.db.flush()
        return c

    # ── спортсмены (AthleteRanking) ────────────────────────────
    def test_athlete_tiebreak_medals_winrate_wins_registration_id(self):
        # Б: 2🥇 + 0🥈 + 10🥉 = 32 > 25 у остальных → выше по медальным очкам.
        b = self._athlete("Б", gold=2, silver=0, bronze=10, wins=1, losses=0)
        # А: 1🥇 + 3🥈 + 5🥉 = 25, винрейт 0.8
        a = self._athlete("А", gold=1, silver=3, bronze=5, wins=4, losses=1, created_at=MIDDLE)
        # В/Г: 25 очков, винрейт 0.9, но В зарегистрирован раньше.
        c = self._athlete("В", gold=1, silver=3, bronze=5, wins=9, losses=1, created_at=MIDDLE)
        d = self._athlete("Г", gold=1, silver=3, bronze=5, wins=9, losses=1, created_at=EARLY)
        # Д: 25 очков, винрейт 0.9, зарегистрирован так же рано, но id больше → ниже Г.
        e = self._athlete("Д", gold=1, silver=3, bronze=5, wins=9, losses=1, created_at=EARLY)
        for athlete in (b, a, c, d, e):
            self.db.add(AthleteRanking(
                athlete_id=athlete.id, points=1000, scope_gender="male", period="all-time",
            ))
        self.db.commit()

        rows = athlete_rankings(period="all-time", gender="male", limit=100, db=self.db)
        order = [r.athlete_name for r in rows]
        # Б — по медальным очкам; В/Г/Д делят 25 и 0.9: Г раньше всех, Д — id выше,
        # В зарегистрирован позже; А — винрейт 0.8 ниже.
        self.assertEqual(order, ["Б", "Г", "Д", "В", "А"])
        self.assertEqual([r.position for r in rows], [1, 2, 3, 4, 5])

    # ── клубы ──────────────────────────────────────────────────
    def test_club_tiebreak_medals_active_registration_id(self):
        x = self._club("Икс", rating_points=1000)
        y = self._club("Игрек", rating_points=1000)
        z = self._club("Зет", rating_points=1000)
        q = self._club("Ку", rating_points=1000, created_at=EARLY)
        k = self._club("Ка", rating_points=1000, created_at=EARLY)
        # Икс: 1🥇 = 6 очков, 1 активный
        self._athlete("С1", club_id=x.id, gold=1, club_active=True)
        # Игрек: 1🥈 = 3 очка → ниже Икс
        self._athlete("С2", club_id=y.id, silver=1, club_active=True)
        # Зет: 1🥇 = 6 очков, 2 активных → выше Икс по числу активных
        self._athlete("С3", club_id=z.id, gold=1, club_active=True)
        self._athlete("С4", club_id=z.id, club_active=True)
        # Ку: 6 очков, 1 активный, но создан раньше → выше Икс
        self._athlete("С5", club_id=q.id, gold=1, club_active=True)
        # Ка: полный твин Ку по статистике, но id больше → ниже Ку
        self._athlete("С6", club_id=k.id, gold=1, club_active=True)
        self.db.commit()

        rows = club_rankings(limit=100, db=self.db)
        order = [r.club_name for r in rows]
        # Зет (активных 2) → Ку/Ка (созданы раньше всех) → Икс → Игрек (3 очка)
        self.assertEqual(order, ["Зет", "Ку", "Ка", "Икс", "Игрек"])
        self.assertEqual([r.position for r in rows], [1, 2, 3, 4, 5])

    # ── тренеры ────────────────────────────────────────────────
    def test_coach_tiebreak_student_medals_active_registration_id(self):
        big = self._coach("Много очков учеников")
        med = self._coach("Больше активных")
        twin_a = self._coach("Твин-А", created_at=EARLY)
        twin_b = self._coach("Твин-Б", created_at=EARLY)
        late = self._coach("Поздний", created_at=MIDDLE)
        # big: 2🥇 учениками = 12 очков
        self._athlete("У1", coach_id=big.id, gold=1)
        self._athlete("У2", coach_id=big.id, gold=1)
        # med: 1🥇 = 6 очков, но 2 активных ученика
        self._athlete("У3", coach_id=med.id, gold=1)
        self._athlete("У4", coach_id=med.id)
        # twin_a / twin_b / late: по 1🥇 = 6 очков, 1 активный
        self._athlete("У5", coach_id=twin_a.id, gold=1)
        self._athlete("У6", coach_id=twin_b.id, gold=1)
        self._athlete("У7", coach_id=late.id, gold=1)
        self.db.commit()

        rows = coach_rankings(limit=100, db=self.db)
        order = [r.coach_name for r in rows]
        # big (12 очков) → med (6 очков, 2 активных) → Твин-А/Б (1 активный,
        # созданы раньше всех) → поздний. Твины делят всё → id решает.
        self.assertEqual(order, ["Много очков учеников", "Больше активных",
                                 "Твин-А", "Твин-Б", "Поздний"])
        self.assertEqual([r.position for r in rows], [1, 2, 3, 4, 5])

    # ── ELO (отображаемый рейтинг спортсменов) ─────────────────
    def test_elo_tiebreak_medals_winrate_wins_registration_id(self):
        # Все с правой рукой 1400.
        m = self._athlete("Медали", elo_right=1400, gold=2, wins=5, losses=2)
        w = self._athlete("Винрейт", elo_right=1400, gold=1, wins=9, losses=1)
        w2 = self._athlete("4-2", elo_right=1400, gold=1, wins=4, losses=2)
        w3 = self._athlete("8-4", elo_right=1400, gold=1, wins=8, losses=4)
        r = self._athlete("Ранний", elo_right=1400, gold=1, wins=8, losses=4, created_at=EARLY)
        i = self._athlete("Ид", elo_right=1400, gold=1, wins=8, losses=4, created_at=EARLY)
        self.db.commit()

        rows = elo_rankings(hand="right", limit=100, db=self.db)
        order = [r.athlete_name for r in rows]
        # Медали 12 → винрейт 0.9 → 0.667 группа: 8-4 и Ранний/Ид делят винрейт
        # (8/12), Ранний зарегистрирован раньше 8-4, Ид — тот же твин, id выше;
        # 4-2 (0.667, но 4 победы < 8) — в конце группы.
        self.assertEqual(order, ["Медали", "Винрейт", "Ранний", "Ид", "8-4", "4-2"])
        self.assertEqual([r.position for r in rows], [1, 2, 3, 4, 5, 6])


if __name__ == "__main__":
    unittest.main()
