"""Хаос-реплей: полный цикл синхронизации турнира из десктопа, прогнанный
дважды подряд (как при потере ответов/офлайн-очереди). Второй прогон не
должен изменить ни одной строки: матчи не задваиваются, Эло не дрейфует,
места и рейтинг клубов остаются теми же (EXPECTED == ACTUAL).

Запуск: python -m pytest tests/integrity -q
"""

import os

os.environ.setdefault("JWT_SECRET", "test-secret-0123456789abcdef0123456789abcdef")
os.environ.setdefault("DESKTOP_SYNC_TOKEN", "test-sync-token")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import unittest
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.router import api_router
from app.core.config import settings
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models.athletes import Athlete
from app.db.models.categories import Category
from app.db.models.competitions import Competition, CompetitionParticipant
from app.db.models.matches import Match
from app.db.models.results import Result
from app.db.models.statistics import AthleteStatistic
from app.db.session import get_db

# 8 участников, single elimination: 4 матча 1/4 + 2 полуфинала + 1 финал.
N = 8


def _build_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(api_router)
    app.dependency_overrides[get_db] = override_db
    return TestClient(app), Session


class ChaosReplayTest(unittest.TestCase):
    """Два полных прогона синхронизации турнира (реплей после потерянных
    ответов). После первого прогона снимаем «слепок» состояния БД; второй
    прогон не должен ничего изменить."""

    @classmethod
    def setUpClass(cls):
        cls.client, cls.Session = _build_client()

    def setUp(self):
        # Полностью очищенная БД на каждый тест (клиент сидит на своём
        # StaticPool-движке — удаляем строки, а не пересоздаём схему).
        session = self.Session()
        try:
            for model in (
                Match, Result, AthleteStatistic, CompetitionParticipant,
                Category, Athlete, Competition,
            ):
                session.query(model).delete(synchronize_session=False)
            session.commit()
        finally:
            session.close()
        # 8 разных спортсменов (как в реальном десктопе: участник привязан
        # к своей карточке).
        self.athlete_ids = []
        for i in range(N):
            r = self.client.post(
                "/api/v1/sync/athletes",
                json={"full_name": f"Спортсмен {i + 1}"},
                headers=self._headers(),
            )
            self.athlete_ids.append(r.json()["id"])

    def _sync_tournament(self, client):
        """Полный цикл: турнир -> категории -> участники -> сетка -> финал
        -> статус completed (финализация). Возвращает (comp_id, cat_id)."""
        r = client.post(
            "/api/v1/sync/competitions",
            json={"name": "Хаос 2026", "date": "2026-08-15"},
            headers=self._headers(),
        )
        comp_id = r.json()["id"]
        r = client.post(
            f"/api/v1/sync/competitions/{comp_id}/categories",
            json={"name": "80 кг", "hand": "Обе"},
            headers=self._headers(),
        )
        cat_id = r.json()["id"]

        pids = []
        for i in range(N):
            r = client.post(
                f"/api/v1/sync/competitions/{comp_id}/participants",
                json={
                    "local_participant_id": 100 + i,
                    "athlete_id": self.athlete_ids[i],
                    "category_id": cat_id,
                },
                headers=self._headers(),
            )
            pids.append(r.json()["id"])

        # Сетка как в десктопе (single elimination): 7 матчей.
        bracket = [
            (0, pids[0], pids[1]),
            (0, pids[2], pids[3]),
            (0, pids[4], pids[5]),
            (0, pids[6], pids[7]),
            (1, None, None),
            (1, None, None),
            (2, None, None),
        ]
        mid_to_id = {}
        for i, (stage, p1, p2) in enumerate(bracket):
            payload = {
                "mid": 1000 + i,
                "category_id": cat_id,
                "hand": "Правая",
                "round_name": f"Раунд {stage}",
                "bracket": "winners",
                "match_order": i % 4,
                "stage": stage,
                "p1_id": p1,
                "p2_id": p2,
            }
            r = client.post("/api/v1/sync/matches", json=payload, headers=self._headers())
            mid_to_id[1000 + i] = r.json()["id"]

        # Текущие пары матчей (как их знает десктоп после продвижений).
        current_pair = {1000 + mid: (p1, p2) for mid, (_, p1, p2) in enumerate(bracket)}

        # Играем: 1/4 финала. (p1/p2 шлём как реальный десктоп — в каждом
        # update_match он резолвит и передаёт обоих участников.)
        def play(mid, winner):
            p1, p2 = current_pair[mid]
            client.patch(
                f"/api/v1/sync/matches/{mid_to_id[mid]}",
                json={"status": "done", "winner_id": winner, "p1_id": p1, "p2_id": p2},
                headers=self._headers(),
            )

        play(1000, pids[0])
        play(1001, pids[2])
        play(1002, pids[4])
        play(1003, pids[6])
        # Победители попадают в полуфиналы.
        current_pair[1004] = (pids[0], pids[2])
        current_pair[1005] = (pids[4], pids[6])
        client.patch(
            f"/api/v1/sync/matches/{mid_to_id[1004]}",
            json={"p1_id": pids[0], "p2_id": pids[2], "status": "pending"},
            headers=self._headers(),
        )
        client.patch(
            f"/api/v1/sync/matches/{mid_to_id[1005]}",
            json={"p1_id": pids[4], "p2_id": pids[6], "status": "pending"},
            headers=self._headers(),
        )
        play(1004, pids[0])
        play(1005, pids[4])
        current_pair[1006] = (pids[0], pids[4])
        client.patch(
            f"/api/v1/sync/matches/{mid_to_id[1006]}",
            json={"p1_id": pids[0], "p2_id": pids[4], "status": "pending"},
            headers=self._headers(),
        )
        play(1006, pids[0])

        client.patch(
            f"/api/v1/sync/competitions/{comp_id}/status",
            json={"status": "completed"},
            headers=self._headers(),
        )
        return comp_id, cat_id

    def _headers(self):
        return {"X-Sync-Token": settings.DESKTOP_SYNC_TOKEN}

    def _snapshot(self):
        """Состояние БД, инвариантное к порядку: (матчи, эло, результаты,
        участники). Для сравнения прогонов."""
        session = self.Session()
        try:
            matches = sorted(
                (m.client_mid, m.status, m.winner_id, m.elo_applied,
                 m.elo_delta_p1, m.elo_delta_p2)
                for m in session.query(Match).all()
            )
            elo = sorted(
                (s.athlete_id, s.elo_left, s.elo_right) for s in session.query(AthleteStatistic).all()
            )
            results = sorted(
                (r.competition_participant_id, r.place, r.medal)
                for r in session.query(Result).all()
            )
            participants = sorted(
                p.id for p in session.query(CompetitionParticipant).all()
            )
            return matches, elo, results, participants
        finally:
            session.close()

    def test_full_tournament_replay_is_identical(self):
        # Прогон 1.
        comp1, cat1 = self._sync_tournament(self.client)
        snap1 = self._snapshot()
        self.assertGreater(len(snap1[0]), 0)
        # Итоги финализации: у каждого из 8 участников своё место (1-8).
        self.assertEqual(len(snap1[2]), N)

        # Прогон 2 (реплей всей синхронизации — как повтор офлайн-очереди
        # после потери ответов). Same tournament: та же самая БД, десктоп
        # посылает те же mids и те же результаты.
        comp2, cat2 = self._sync_tournament(self.client)
        self.assertEqual(comp1, comp2)
        snap2 = self._snapshot()

        # Каждое изменение в прогоне 2 было идемпотентным: состояние БД
        # побайтово то же (EXPECTED == ACTUAL).
        self.assertEqual(snap1, snap2)

    def test_batch_replay_keeps_state(self):
        comp_id, cat_id = self._sync_tournament(self.client)
        snap1 = self._snapshot()
        # Повторный прогон через batch-endpoint: те же матчи, те же mid.
        payload = {"matches": []}
        for i in range(7):
            payload["matches"].append({
                "mid": 1000 + i,
                "category_id": cat_id,
                "hand": "Правая",
                "round_name": f"Раунд {i % 3}",
                "bracket": "winners",
                "match_order": i % 4,
                "stage": i % 3,
            })
        r = self.client.post(
            "/api/v1/sync/matches/batch", json=payload, headers=self._headers()
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self._snapshot(), snap1)


if __name__ == "__main__":
    unittest.main()
