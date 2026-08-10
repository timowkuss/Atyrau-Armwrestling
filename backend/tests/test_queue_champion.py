"""Проверка новой серверной логики чемпиона в живом табло /queue.

Раньше чемпион искался по win_next_id IS NULL (связи матчей на сервер
не синкаются — у всех матчей win_next_id == NULL), поэтому победитель
первого же матча 1/4 объявлялся чемпионом и висел на 1-м месте, хотя
турнир не завершён. Теперь чемпион SE = победитель done-матча с
максимальным stage во всей категории (финал существует с момента
генерации сетки), поэтому пока финал не сыгран — чемпиона нет.

Запуск:  backend/venv/Scripts/python -m unittest tests.test_queue_champion -v
"""
from __future__ import annotations

import os
import unittest
from datetime import date

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DESKTOP_SYNC_TOKEN", "test-sync-token")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
import app.db.models  # noqa: F401
from app.db.models.athletes import Athlete
from app.db.models.categories import Category
from app.db.models.competitions import Competition, CompetitionParticipant
from app.db.models.matches import Match
from app.db.models.statistics import AthleteStatistic


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _participant(db, comp, cat, name):
    a = Athlete(full_name=name)
    db.add(a)
    db.flush()
    db.add(AthleteStatistic(athlete_id=a.id))
    p = CompetitionParticipant(
        competition_id=comp.id, category_id=cat.id, athlete_id=a.id,
    )
    db.add(p)
    db.flush()
    return p


def _match(db, comp, cat, stage, order, p1, p2, winner, status="pending"):
    m = Match(
        competition_id=comp.id, category_id=cat.id, hand="Правая",
        bracket="winners", stage=stage, match_order=order,
        status=status, table_number=1,
        p1_id=p1.id if p1 else None, p2_id=p2.id if p2 else None,
        winner_id=winner.id if winner else None,
    )
    db.add(m)
    db.flush()
    return m


class ChampionLogicTest(unittest.TestCase):
    def setUp(self):
        self.db = _session()
        self.comp = Competition(name="Чемпионат", date=date(2026, 1, 1), status="published")
        self.db.add(self.comp)
        self.db.flush()
        self.cat = Category(competition_id=self.comp.id, name="55 кг", hand="Правая")
        self.db.add(self.cat)
        self.db.flush()
        # 8 участников: 4 матча 1/4 (stage 0), 2 полуфинала (stage 1), 1 финал (stage 2)
        self.ps = [self._p(f"Боец {i + 1}") for i in range(8)]
        self._bracket()

    def _p(self, name):
        return _participant(self.db, self.comp, self.cat, name)

    def _bracket(self):
        for i in range(4):
            _match(self.db, self.comp, self.cat, 0, i,
                   self.ps[2 * i], self.ps[2 * i + 1], None)
        for i in range(2):
            _match(self.db, self.comp, self.cat, 1, i, None, None, None)
        _match(self.db, self.comp, self.cat, 2, 0, None, None, None)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _queue(self):
        from app.api.v1.public.competitions import get_competition_queue
        return get_competition_queue(self.comp.id, self.db)

    def _eliminated(self):
        data = self._queue()
        table = data[0]
        return [
            {"athlete_name": e.athlete_name, "place": e.place}
            for e in table.eliminated
        ]

    def test_quarterfinal_winner_is_not_champion(self):
        """Победитель первого матча 1/4 НЕ должен получить 1-е место."""
        _match(self.db, self.comp, self.cat, 0, 0,
               self.ps[0], self.ps[1], self.ps[0], status="done")
        self.db.commit()
        names = [(e["athlete_name"], e["place"]) for e in self._eliminated()]
        # Победитель 1/4 ещё не выбыл — его в выдаче нет (турнир не завершён).
        self.assertFalse(any(n == "Боец 1" for n, _ in names))
        self.assertTrue(names)  # проигравший 1/4 есть

    def test_champion_only_after_final(self):
        """Чемпион появляется только после сыгранного финала (stage = max)."""
        # Доигрываем полуфиналы + финал
        for i in range(2):
            _match(self.db, self.comp, self.cat, 1, i,
                   self.ps[0], self.ps[2], self.ps[0], status="done")
        _match(self.db, self.comp, self.cat, 2, 0,
               self.ps[0], self.ps[4], self.ps[0], status="done")
        self.db.commit()
        names = [(e["athlete_name"], e["place"]) for e in self._eliminated()]
        champ = [n for n, p in names if p == 1]
        self.assertEqual(champ, ["Боец 1"])


if __name__ == "__main__":
    unittest.main()
