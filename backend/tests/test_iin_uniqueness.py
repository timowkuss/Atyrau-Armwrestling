"""Тесты уникальности ИИН в админских эндпоинтах.

Запуск:  backend/venv/Scripts/python -m unittest tests.test_iin_uniqueness -v

Вызывает функции эндпоинтов напрямую (без HTTP), проверяет что:
  - нельзя создать второго спортсмена/тренера с тем же ИИН (400);
  - при редактировании свой же ИИН не считается дубликатом;
  - один человек может быть И тренером, И спортсменом (разные таблицы).
"""
from __future__ import annotations

import os
import unittest
from datetime import date

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DESKTOP_SYNC_TOKEN", "test-sync-token")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
import app.db.models  # noqa: F401  (регистрирует все модели в Base.metadata)
from app.db.models.athletes import Athlete
from app.db.models.coaches import Coach
from app.schemas.athletes import AthleteCreate, AthleteUpdate
from app.schemas.coaches import CoachCreate
from app.schemas.sync import (
    AthleteSyncCreate,
    AthleteSyncUpdate,
    CoachSyncCreate,
    CoachSyncUpdate,
)
from app.api.v1.admin.athletes import create_athlete, update_athlete
from app.api.v1.admin.coaches import create_coach
from app.api.v1.sync.athletes import (
    create_athlete as sync_create_athlete,
    update_athlete as sync_update_athlete,
)
from app.api.v1.sync.coaches import (
    create_coach as sync_create_coach,
    update_coach as sync_update_coach,
)


class IinUniquenessTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self._factory = sessionmaker(bind=engine, autoflush=False)
        self._engine = engine

        self.db = self._factory()
        self.db.add(Athlete(full_name="Иван Петров", iin="123456789012"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self._engine.dispose()

    def _athlete_id_by_iin(self, iin):
        return self.db.query(Athlete).filter(Athlete.iin == iin).first().id

    def test_create_athlete_dup_iin_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            create_athlete(
                AthleteCreate(full_name="Другой Человек", iin="123456789012"),
                self.db, None)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("ИИН", ctx.exception.detail)

    def test_create_athlete_new_iin_ok(self):
        res = create_athlete(
            AthleteCreate(full_name="Новый Спортсмен", iin="999999999999"),
            self.db, None)
        self.assertIn("id", res)

    def test_update_athlete_own_iin_ok_and_dup_rejected(self):
        own_id = self._athlete_id_by_iin("123456789012")
        # свой же ИИН при редактировании — не дубликат
        res = update_athlete(
            own_id, AthleteUpdate(full_name="Иван Петров 2"), self.db, None)
        self.assertEqual(res["status"], "ok")

        # другой спортсмен пытается взять занятый ИИН
        other_id = create_athlete(
            AthleteCreate(full_name="Другой", iin="111111111111"), self.db, None)["id"]
        with self.assertRaises(HTTPException) as ctx:
            update_athlete(
                other_id, AthleteUpdate(iin="123456789012"), self.db, None)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_coach_athlete_same_iin_allowed(self):
        # тренер может иметь тот же ИИН, что и спортсмен (один человек)
        res = create_coach(
            CoachCreate(
                first_name="Иван", last_name="Петров",
                birth_date=date(1990, 1, 1), iin="123456789012",
            ),
            self.db, None)
        self.assertIn("id", res)

    def test_create_coach_dup_iin_rejected(self):
        create_coach(
            CoachCreate(
                first_name="Тренер", last_name="Первый",
                birth_date=date(1980, 1, 1), iin="111111111111",
            ),
            self.db, None)
        with self.assertRaises(HTTPException) as ctx:
            create_coach(
                CoachCreate(
                    first_name="Тренер", last_name="Второй",
                    birth_date=date(1981, 1, 1), iin="111111111111",
                ),
                self.db, None)
        self.assertEqual(ctx.exception.status_code, 400)

    # ── sync-эндпоинты (десктоп → сервер) ──────────────────────
    def test_sync_create_athlete_dup_iin_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            sync_create_athlete(
                AthleteSyncCreate(full_name="Другой", iin="123456789012"),
                self.db, True)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_sync_update_athlete_dup_iin_rejected(self):
        other_id = sync_create_athlete(
            AthleteSyncCreate(full_name="Другой", iin="111111111111"),
            self.db, True)["id"]
        with self.assertRaises(HTTPException) as ctx:
            sync_update_athlete(
                other_id, AthleteSyncUpdate(iin="123456789012"), self.db, True)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_erase_iin_becomes_null(self):
        # стирание ИИН в админке шлёт '' — бэкенд обязан сохранить NULL,
        # иначе два пустых ИИН нарушат unique-constraint.
        own_id = self._athlete_id_by_iin("123456789012")
        res = update_athlete(own_id, AthleteUpdate(iin=""), self.db, None)
        self.assertEqual(res["status"], "ok")
        self.assertIsNone(self.db.query(Athlete).filter(Athlete.id == own_id).first().iin)

        # второй спортсмен тоже стирает — без IntegrityError
        other_id = create_athlete(
            AthleteCreate(full_name="Другой", iin="111111111111"), self.db, None)["id"]
        res2 = update_athlete(other_id, AthleteUpdate(iin=""), self.db, None)
        self.assertEqual(res2["status"], "ok")
        self.assertIsNone(self.db.query(Athlete).filter(Athlete.id == other_id).first().iin)

    def test_sync_create_coach_dup_iin_rejected(self):
        sync_create_coach(
            CoachSyncCreate(full_name="Тренер Один", iin="111111111111"),
            self.db, True)
        with self.assertRaises(HTTPException) as ctx:
            sync_create_coach(
                CoachSyncCreate(full_name="Тренер Два", iin="111111111111"),
                self.db, True)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_sync_update_coach_dup_iin_rejected(self):
        cid1 = sync_create_coach(
            CoachSyncCreate(full_name="Тренер Один", iin="111111111111"),
            self.db, True)["id"]
        sync_create_coach(
            CoachSyncCreate(full_name="Тренер Два", iin="222222222222"),
            self.db, True)
        with self.assertRaises(HTTPException) as ctx:
            sync_update_coach(
                cid1, CoachSyncUpdate(iin="222222222222"), self.db, True)
        self.assertEqual(ctx.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
