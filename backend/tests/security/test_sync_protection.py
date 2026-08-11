"""Sync-эндпоинты: участники матча обязаны принадлежать его категории,
лишние поля отклоняются, без токена — 401.

Запуск: python -m pytest tests/security -q
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


class SyncProtectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client, cls.Session = _build_client()
        session = cls.Session()
        comp = Competition(name="Турнир", date=date(2026, 8, 1), status="draft")
        session.add(comp)
        session.flush()
        cat_a = Category(name="80 кг", competition_id=comp.id)
        cat_b = Category(name="90 кг", competition_id=comp.id)
        session.add_all([cat_a, cat_b])
        session.flush()
        cls.comp_id = comp.id
        cls.cat_a_id = cat_a.id
        cls.cat_b_id = cat_b.id

        def participant(category_id):
            athlete = Athlete(full_name="А")
            session.add(athlete)
            session.flush()
            p = CompetitionParticipant(
                competition_id=comp.id,
                category_id=category_id,
                athlete_id=athlete.id,
            )
            session.add(p)
            session.flush()
            return p.id

        cls.p1 = participant(cat_a.id)
        cls.p2 = participant(cat_a.id)
        cls.foreign = participant(cat_b.id)
        session.commit()
        session.close()

    def _headers(self):
        return {"X-Sync-Token": settings.DESKTOP_SYNC_TOKEN}

    def test_no_token_401(self):
        r = self.client.post(
            "/api/v1/sync/matches",
            json={"category_id": self.cat_a_id},
        )
        self.assertEqual(r.status_code, 401)

    def test_wrong_token_401(self):
        r = self.client.post(
            "/api/v1/sync/matches",
            json={"category_id": self.cat_a_id},
            headers={"X-Sync-Token": "wrong-token"},
        )
        self.assertEqual(r.status_code, 401)

    def test_valid_match_created(self):
        r = self.client.post(
            "/api/v1/sync/matches",
            json={
                "category_id": self.cat_a_id,
                "p1_id": self.p1,
                "p2_id": self.p2,
                "winner_id": self.p1,
            },
            headers=self._headers(),
        )
        self.assertEqual(r.status_code, 201)
        self.assertIn("id", r.json())

    def test_participant_from_other_category_422(self):
        # Участник чужой категории «вписывается» в матч — 422.
        r = self.client.post(
            "/api/v1/sync/matches",
            json={
                "category_id": self.cat_a_id,
                "p1_id": self.p1,
                "p2_id": self.foreign,
            },
            headers=self._headers(),
        )
        self.assertEqual(r.status_code, 422)

    def test_winner_not_in_pair_422(self):
        r = self.client.post(
            "/api/v1/sync/matches",
            json={
                "category_id": self.cat_a_id,
                "p1_id": self.p1,
                "p2_id": self.p2,
                "winner_id": self.foreign,
            },
            headers=self._headers(),
        )
        self.assertEqual(r.status_code, 422)

    def test_extra_field_422(self):
        # mass assignment через неизвестное поле в sync-схеме.
        r = self.client.post(
            "/api/v1/sync/matches",
            json={"category_id": self.cat_a_id, "evil_field": "x"},
            headers=self._headers(),
        )
        self.assertEqual(r.status_code, 422)

    def test_batch_with_foreign_participant_422(self):
        r = self.client.post(
            "/api/v1/sync/matches/batch",
            json={
                "matches": [
                    {
                        "category_id": self.cat_a_id,
                        "p1_id": self.p1,
                        "p2_id": self.foreign,
                    }
                ]
            },
            headers=self._headers(),
        )
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()
