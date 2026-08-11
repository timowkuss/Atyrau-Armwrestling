"""Идемпотентность создания при ретраях (потерянный ответ -> повтор из
офлайн-очереди десктопа): матчи по (category_id, mid), турнир/категория/
участник по естественным ключам. Плюс проверка, что «dict,404» кортежи
исправлены (JSON 404 вместо нестандартного тела).

Запуск: python -m pytest tests/integrity -q
"""

import os

os.environ.setdefault(
    "JWT_SECRET", "test-secret-0123456789abcdef0123456789abcdef"
)
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
from app.db.models.statistics import AthleteStatistic
from app.db.session import get_db


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


class MatchReplayIdempotencyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client, cls.Session = _build_client()
        session = cls.Session()
        comp = Competition(name="Турнир", date=date(2026, 8, 1), status="in_progress")
        session.add(comp)
        session.flush()
        cat = Category(name="80 кг", competition_id=comp.id, hand="Правая")
        session.add(cat)
        session.flush()

        def participant(full_name):
            athlete = Athlete(full_name=full_name)
            session.add(athlete)
            session.flush()
            session.add(
                AthleteStatistic(athlete_id=athlete.id, elo_left=1000, elo_right=1000)
            )
            p = CompetitionParticipant(
                competition_id=comp.id, category_id=cat.id, athlete_id=athlete.id
            )
            session.add(p)
            session.flush()
            return p.id

        cls.comp_id = comp.id
        cls.cat_id = cat.id
        cls.p1 = participant("Иван Иванов")
        cls.p2 = participant("Пётр Петров")
        session.commit()
        session.close()

    def _headers(self):
        return {"X-Sync-Token": settings.DESKTOP_SYNC_TOKEN}

    def _match_payload(self, mid, **extra):
        payload = {
            "mid": mid,
            "category_id": self.cat_id,
            "p1_id": self.p1,
            "p2_id": self.p2,
        }
        payload.update(extra)
        return payload

    def _match_count(self, mid=None):
        """Число матчей по client_mid (None — матчи без mid). БД общая на
        класс, поэтому считаем только записи конкретного теста."""
        session = self.Session()
        try:
            q = session.query(Match)
            if mid is None:
                q = q.filter(Match.client_mid.is_(None))
            else:
                q = q.filter(Match.client_mid == mid)
            return q.count()
        finally:
            session.close()

    def test_replay_returns_same_match(self):
        first = self.client.post(
            "/api/v1/sync/matches", json=self._match_payload(101), headers=self._headers()
        )
        self.assertEqual(first.status_code, 201)
        replay = self.client.post(
            "/api/v1/sync/matches", json=self._match_payload(101), headers=self._headers()
        )
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay.json()["id"], first.json()["id"])
        self.assertEqual(replay.json()["status"], "existing")
        self.assertEqual(self._match_count(mid=101), 1)

    def test_replay_does_not_double_elo(self):
        # победа p1: elo применяется один раз, повтор create_match (потерянный
        # ответ) ничего не начисляет повторно.
        r = self.client.post(
            "/api/v1/sync/matches",
            json=self._match_payload(202, winner_id=self.p1, status="done"),
            headers=self._headers(),
        )
        self.assertEqual(r.status_code, 201)

        session = self.Session()
        try:
            elo_after_first = {
                s.athlete_id: s.elo_left
                for s in session.query(AthleteStatistic).all()
            }
        finally:
            session.close()

        self.client.post(
            "/api/v1/sync/matches",
            json=self._match_payload(202, winner_id=self.p1, status="done"),
            headers=self._headers(),
        )
        session = self.Session()
        try:
            elo_after_replay = {
                s.athlete_id: s.elo_left
                for s in session.query(AthleteStatistic).all()
            }
        finally:
            session.close()

        self.assertEqual(elo_after_first, elo_after_replay)

    def test_batch_replay_same_ids(self):
        payload = {
            "matches": [
                self._match_payload(301),
                self._match_payload(302),
                self._match_payload(303),
            ]
        }
        first = self.client.post(
            "/api/v1/sync/matches/batch", json=payload, headers=self._headers()
        )
        self.assertEqual(first.status_code, 201)
        ids_first = first.json()["ids"]

        replay = self.client.post(
            "/api/v1/sync/matches/batch", json=payload, headers=self._headers()
        )
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(sorted(replay.json()["ids"]), sorted(ids_first))
        for mid in (301, 302, 303):
            self.assertEqual(self._match_count(mid=mid), 1)

    def test_batch_internal_duplicates_collapsed(self):
        payload = {
            "matches": [
                self._match_payload(401),
                self._match_payload(401),
                self._match_payload(402),
            ]
        }
        r = self.client.post(
            "/api/v1/sync/matches/batch", json=payload, headers=self._headers()
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(len(r.json()["ids"]), 2)
        self.assertEqual(self._match_count(mid=401), 1)
        self.assertEqual(self._match_count(mid=402), 1)

    def test_without_mid_legacy_behavior(self):
        # Старые клиенты без mid: дубли возможны, но не ломают существующий
        # путь (именно для них mid и вводится).
        self.client.post(
            "/api/v1/sync/matches",
            json={"category_id": self.cat_id, "p1_id": self.p1, "p2_id": self.p2},
            headers=self._headers(),
        )
        self.client.post(
            "/api/v1/sync/matches",
            json={"category_id": self.cat_id, "p1_id": self.p1, "p2_id": self.p2},
            headers=self._headers(),
        )
        self.assertEqual(self._match_count(mid=None), 2)


class CompetitionReplayIdempotencyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client, cls.Session = _build_client()
        session = cls.Session()
        athlete = Athlete(full_name="Сидор Сидоров")
        session.add(athlete)
        session.flush()
        session.add(AthleteStatistic(athlete_id=athlete.id))
        cls.athlete_id = athlete.id
        session.commit()
        session.close()

    def _headers(self):
        return {"X-Sync-Token": settings.DESKTOP_SYNC_TOKEN}

    def test_competition_replay_same_id(self):
        payload = {"name": "Чемпионат 2026", "date": "2026-09-01"}
        first = self.client.post(
            "/api/v1/sync/competitions", json=payload, headers=self._headers()
        )
        replay = self.client.post(
            "/api/v1/sync/competitions", json=payload, headers=self._headers()
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay.json()["id"], first.json()["id"])
        session = self.Session()
        try:
            self.assertEqual(
                session.query(Competition)
                .filter(Competition.name == "Чемпионат 2026")
                .count(),
                1,
            )
        finally:
            session.close()

    def test_category_replay_same_id(self):
        r = self.client.post(
            "/api/v1/sync/competitions",
            json={"name": "Турнир Категорий", "date": "2026-10-01"},
            headers=self._headers(),
        )
        comp_id = r.json()["id"]
        payload = {"name": "90 кг", "hand": "Левая"}
        first = self.client.post(
            f"/api/v1/sync/competitions/{comp_id}/categories",
            json=payload,
            headers=self._headers(),
        )
        replay = self.client.post(
            f"/api/v1/sync/competitions/{comp_id}/categories",
            json=payload,
            headers=self._headers(),
        )
        self.assertEqual(first.json()["id"], replay.json()["id"])
        session = self.Session()
        try:
            self.assertEqual(
                session.query(Category)
                .filter(Category.competition_id == comp_id)
                .count(),
                1,
            )
        finally:
            session.close()

    def test_participant_replay_same_id(self):
        r = self.client.post(
            "/api/v1/sync/competitions",
            json={"name": "Турнир Участников", "date": "2026-11-01"},
            headers=self._headers(),
        )
        comp_id = r.json()["id"]
        cat = self.client.post(
            f"/api/v1/sync/competitions/{comp_id}/categories",
            json={"name": "100 кг"},
            headers=self._headers(),
        )
        cat_id = cat.json()["id"]
        payload = {
            "local_participant_id": 1,
            "athlete_id": self.athlete_id,
            "category_id": cat_id,
        }
        first = self.client.post(
            f"/api/v1/sync/competitions/{comp_id}/participants",
            json=payload,
            headers=self._headers(),
        )
        replay = self.client.post(
            f"/api/v1/sync/competitions/{comp_id}/participants",
            json=payload,
            headers=self._headers(),
        )
        self.assertEqual(first.json()["id"], replay.json()["id"])
        session = self.Session()
        try:
            self.assertEqual(
                session.query(CompetitionParticipant)
                .filter(CompetitionParticipant.competition_id == comp_id)
                .count(),
                1,
            )
        finally:
            session.close()

    def test_missing_entities_return_json_404(self):
        # Бывшие «dict,404» кортежи: теперь стандартный JSON 404.
        for method, url in [
            ("patch", "/api/v1/sync/athletes/99999"),
            ("patch", "/api/v1/sync/coaches/99999"),
            ("patch", "/api/v1/sync/clubs/99999"),
        ]:
            r = self.client.request(method, url, json={}, headers=self._headers())
            self.assertEqual(r.status_code, 404, url)
            body = r.json()
            self.assertIn("detail", body, url)


if __name__ == "__main__":
    unittest.main()
