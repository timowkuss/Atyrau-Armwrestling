"""Эндпоинты: черновики и скрытые спортсмены не отдаются публично,
пагинация ограничена.

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
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models.athletes import Athlete
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


class PublicExposureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client, cls.Session = _build_client()
        session = cls.Session()
        cls.draft_id = cls._add_competition(session, status="draft")
        cls.published_id = cls._add_competition(session, status="published")
        cls.hidden_athlete_id = cls._add_athlete(session, hidden=True)
        cls.visible_athlete_id = cls._add_athlete(session, hidden=False)
        session.commit()
        session.close()

    @staticmethod
    def _add_competition(session, status: str) -> int:
        comp = Competition(
            name="Турнир", date=date(2026, 8, 1), status=status
        )
        session.add(comp)
        session.flush()
        return comp.id

    @staticmethod
    def _add_athlete(session, hidden: bool) -> int:
        athlete = Athlete(full_name="А", is_hidden=hidden)
        session.add(athlete)
        session.flush()
        return athlete.id

    # ── Черновики не публикуются ────────────────────────────────────
    def test_draft_competition_404(self):
        r = self.client.get(f"/api/v1/public/competitions/{self.draft_id}")
        self.assertEqual(r.status_code, 404)

    def test_published_competition_200(self):
        r = self.client.get(f"/api/v1/public/competitions/{self.published_id}")
        self.assertEqual(r.status_code, 200)

    def test_draft_not_in_list(self):
        r = self.client.get("/api/v1/public/competitions")
        self.assertEqual(r.status_code, 200)
        ids = [c["id"] for c in r.json()["items"]]
        self.assertNotIn(self.draft_id, ids)
        self.assertIn(self.published_id, ids)

    # ── Скрытые спортсмены не отдаются по прямым ссылкам ────────────
    def test_hidden_athlete_history_404(self):
        r = self.client.get(
            f"/api/v1/public/athletes/{self.hidden_athlete_id}/history"
        )
        self.assertEqual(r.status_code, 404)

    def test_hidden_athlete_elo_history_404(self):
        r = self.client.get(
            f"/api/v1/public/athletes/{self.hidden_athlete_id}/elo-history"
        )
        self.assertEqual(r.status_code, 404)

    def test_hidden_athlete_matches_404(self):
        r = self.client.get(
            f"/api/v1/public/athletes/{self.hidden_athlete_id}/matches"
        )
        self.assertEqual(r.status_code, 404)

    def test_visible_athlete_history_200(self):
        r = self.client.get(
            f"/api/v1/public/athletes/{self.visible_athlete_id}/history"
        )
        self.assertEqual(r.status_code, 200)

    # ── Пагинация ограничена ────────────────────────────────────────
    def test_page_size_too_big_422(self):
        r = self.client.get("/api/v1/public/athletes", params={"page_size": 1000})
        self.assertEqual(r.status_code, 422)

    def test_page_size_zero_422(self):
        r = self.client.get("/api/v1/public/athletes", params={"page_size": 0})
        self.assertEqual(r.status_code, 422)

    def test_page_zero_422(self):
        r = self.client.get("/api/v1/public/athletes", params={"page": 0})
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()
