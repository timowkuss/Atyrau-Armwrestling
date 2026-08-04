"""Дедуп клубов по имени в create_club (sync + admin).

Запуск:  backend/venv/Scripts/python -m unittest tests.test_club_dedupe -v

После расчистки дублей (миграция b1c2d3e4f5a6) повторное создание клуба
с уже существующим именем (без учёта регистра) не должно плодить строки:
возвращается id существующего клуба. Проверяем оба эндпоинта.
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
import app.db.models  # noqa: F401
from app.db.models.clubs import Club
from app.schemas.sync import ClubSyncCreate
from app.schemas.clubs import ClubCreate
from app.api.v1.sync.clubs import create_club as sync_create_club
from app.api.v1.admin.clubs import create_club as admin_create_club


class ClubDedupeTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self._engine = engine
        self.db = sessionmaker(bind=engine, autoflush=False)()

    def tearDown(self):
        self.db.close()
        self._engine.dispose()

    def test_sync_create_club_dedupes_by_name(self):
        first = sync_create_club(ClubSyncCreate(name="Алга"), self.db, _=True)
        second = sync_create_club(ClubSyncCreate(name="Алга"), self.db, _=True)
        third = sync_create_club(ClubSyncCreate(name="АЛГА"), self.db, _=True)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["id"], third["id"])
        self.assertEqual(self.db.query(Club).count(), 1)

    def test_sync_create_club_different_names_ok(self):
        sync_create_club(ClubSyncCreate(name="Алга"), self.db, _=True)
        sync_create_club(ClubSyncCreate(name="Олимп"), self.db, _=True)
        self.assertEqual(self.db.query(Club).count(), 2)

    def test_admin_create_club_dedupes_by_name(self):
        first = admin_create_club(
            ClubCreate(name="Олимп", city_id=1), self.db, _=True
        )
        second = admin_create_club(
            ClubCreate(name="олимп", city_id=1), self.db, _=True
        )
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(self.db.query(Club).count(), 1)


if __name__ == "__main__":
    unittest.main()
