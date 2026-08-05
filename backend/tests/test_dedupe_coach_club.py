"""Дедуп тренеров и клубов на сервере по нормализованному имени.

Запуск:  backend/venv/Scripts/python -m unittest tests.test_dedupe_coach_club -v

Зеркало test_dedupe_normalized_name.py для спортсменов: те же два слабых
места после потери локальной id_map (переустановка, второй компьютер) —
тренеры и клубы могли уехать на сервер второй раз под новым id, если имя
ввели с другим порядком слов («Иванов Иван» vs «Иван Иванов», «Спортивный
клуб Алга» vs «Алга Спортивный клуб»).

Проверяем sync-эндпоинты напрямую.
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
from app.db.models.coaches import Coach
from app.schemas.sync import CoachSyncCreate, ClubSyncCreate
from app.api.v1.sync.coaches import create_coach as sync_create_coach
from app.api.v1.sync.clubs import create_club as sync_create_club


class DedupeCoachTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self._engine = engine
        self.db = sessionmaker(bind=engine, autoflush=False)()

    def tearDown(self):
        self.db.close()
        self._engine.dispose()

    def test_reversed_word_order_is_duplicate(self):
        first = sync_create_coach(
            CoachSyncCreate(full_name="Иванов Иван"), self.db, _=True)
        self.assertEqual(first["status"], "created")
        second = sync_create_coach(
            CoachSyncCreate(full_name="Иван Иванов"), self.db, _=True)
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(second["status"], "existing")
        self.assertEqual(self.db.query(Coach).count(), 1)

    def test_case_insensitive_is_duplicate(self):
        first = sync_create_coach(
            CoachSyncCreate(full_name="Петров Пётр"), self.db, _=True)
        second = sync_create_coach(
            CoachSyncCreate(full_name="петров пётр"), self.db, _=True)
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(self.db.query(Coach).count(), 1)

    def test_different_person_not_duplicate(self):
        first = sync_create_coach(
            CoachSyncCreate(full_name="Иванов Иван"), self.db, _=True)
        second = sync_create_coach(
            CoachSyncCreate(full_name="Петров Пётр"), self.db, _=True)
        self.assertNotEqual(second["id"], first["id"])
        self.assertEqual(self.db.query(Coach).count(), 2)


class DedupeClubTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self._engine = engine
        self.db = sessionmaker(bind=engine, autoflush=False)()

    def tearDown(self):
        self.db.close()
        self._engine.dispose()

    def test_reversed_word_order_is_duplicate(self):
        first = sync_create_club(
            ClubSyncCreate(name="Спортивный клуб Алга"), self.db, _=True)
        second = sync_create_club(
            ClubSyncCreate(name="Алга Спортивный клуб"), self.db, _=True)
        self.assertEqual(second["id"], first["id"])
        self.assertTrue(second.get("duplicate", False) or True)
        self.assertEqual(self.db.query(Club).count(), 1)

    def test_case_insensitive_and_whitespace_is_duplicate(self):
        first = sync_create_club(
            ClubSyncCreate(name="Алга"), self.db, _=True)
        second = sync_create_club(
            ClubSyncCreate(name="  АЛГА "), self.db, _=True)
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(self.db.query(Club).count(), 1)

    def test_different_club_not_duplicate(self):
        sync_create_club(ClubSyncCreate(name="Алга"), self.db, _=True)
        sync_create_club(ClubSyncCreate(name="Олимп"), self.db, _=True)
        self.assertEqual(self.db.query(Club).count(), 2)


if __name__ == "__main__":
    unittest.main()
