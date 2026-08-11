"""Каскадные изменения при скрытии/удалении спортсменов и тренеров.

Запуск:  backend/venv/Scripts/python -m unittest tests.test_hide_and_cascade -v

Проверяет сквозную логику (админка + публичный сайт + sync-десктоп):
  - скрытие/удаление спортсмена → выход из клуба (штраф -10) и от тренера;
  - скрытие/удаление тренера → все ученики остаются без тренера, тренер
    выходит из клуба;
  - скрытые карточки не попадают на публичный сайт, но видны в админке
    и в sync-changes (десктоп подтянет их в секцию «Скрытые»);
  - повторное скрытие не задваивает штраф клубу (идемпотентность).

Вызывает функции эндпоинтов напрямую (без HTTP), как test_iin_uniqueness.py.
"""
from __future__ import annotations

import os
import unittest
from datetime import date

os.environ.setdefault("JWT_SECRET", "test-secret-0123456789abcdef0123456789abcdef")
os.environ.setdefault("DESKTOP_SYNC_TOKEN", "test-sync-token")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
import app.db.models  # noqa: F401  (регистрирует все модели в Base.metadata)
from app.db.models.athletes import Athlete
from app.db.models.categories import Category
from app.db.models.club_rating import ClubRatingHistory
from app.db.models.clubs import Club
from app.db.models.coaches import Coach
from app.db.models.competitions import Competition, CompetitionParticipant
from app.db.models.statistics import AthleteStatistic
from app.schemas.athletes import AthleteUpdate
from app.schemas.coaches import CoachUpdate
from app.schemas.sync import AthleteSyncUpdate, CoachSyncUpdate
from app.api.v1.admin.athletes import (
    delete_athlete as admin_delete_athlete,
    list_athletes_admin,
    update_athlete as admin_update_athlete,
)
from app.api.v1.admin.coaches import (
    delete_coach as admin_delete_coach,
    list_coaches_admin,
    update_coach as admin_update_coach,
)
from app.api.v1.public.coaches import (
    get_coach as public_get_coach,
    list_coaches as public_list_coaches,
)
from app.api.v1.public.clubs import get_club as public_get_club
from app.api.v1.sync.athletes import (
    delete_athlete as sync_delete_athlete,
    get_athlete_changes,
    update_athlete as sync_update_athlete,
)
from app.api.v1.sync.coaches import (
    delete_coach as sync_delete_coach,
    get_coach_changes,
    update_coach as sync_update_coach,
)
from app.services import club_rating as cr


def _rating_history(db, club_id, reason):
    return (
        db.query(ClubRatingHistory)
        .filter(ClubRatingHistory.club_id == club_id, ClubRatingHistory.reason == reason)
        .count()
    )


class HideAndCascadeTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self._engine = engine
        self.db = sessionmaker(bind=engine, autoflush=False)()

    def tearDown(self):
        self.db.close()
        self._engine.dispose()

    # ── фабрики ────────────────────────────────────────────────
    def _club(self, name="Клуб"):
        club = Club(name=name)
        self.db.add(club)
        self.db.flush()
        return club

    def _coach(self, club_id=None, full_name="Тренер Тестов"):
        coach = Coach(full_name=full_name, club_id=club_id)
        self.db.add(coach)
        self.db.flush()
        return coach

    def _athlete(self, club_id=None, coach_id=None, full_name="Спортсмен Тестов"):
        athlete = Athlete(
            full_name=full_name,
            club_id=club_id,
            coach_id=coach_id,
            join_club_date=date.today() if club_id else None,
        )
        self.db.add(athlete)
        self.db.flush()
        self.db.add(AthleteStatistic(athlete_id=athlete.id))
        self.db.commit()
        return athlete

    def _give_club_points(self, club_id, athlete_id, points=100):
        cr.add_points(self.db, club_id, athlete_id, None, points, "SEED", "seed")
        self.db.commit()

    def _participant(self, athlete_id):
        comp = Competition(name="Турнир", date=date(2026, 1, 15))
        self.db.add(comp)
        self.db.flush()
        cat = Category(competition_id=comp.id, name="Абсолютная")
        self.db.add(cat)
        self.db.flush()
        self.db.add(
            CompetitionParticipant(competition_id=comp.id, athlete_id=athlete_id, category_id=cat.id)
        )
        self.db.commit()

    def _coach_by_name(self, name):
        return self.db.query(Coach).filter(Coach.full_name == name).one()

    # ═══ ТРЕНЕР ═════════════════════════════════════════════════
    def test_admin_hide_coach_releases_students_and_leaves_club(self):
        club = self._club()
        coach = self._coach(club_id=club.id, full_name="Тренер А")
        s1 = self._athlete(club_id=club.id, coach_id=coach.id, full_name="Ученик 1")
        s2 = self._athlete(club_id=club.id, coach_id=coach.id, full_name="Ученик 2")

        res = admin_update_coach(coach.id, CoachUpdate(is_hidden=True), self.db, None)
        self.assertEqual(res["status"], "ok")

        coach = self.db.query(Coach).get(coach.id)
        self.assertTrue(coach.is_hidden)
        self.assertIsNone(coach.club_id)
        # ученики отпущены
        self.assertIsNone(self.db.query(Athlete).get(s1.id).coach_id)
        self.assertIsNone(self.db.query(Athlete).get(s2.id).coach_id)
        # а их клубная привязка не тронута (трогается только тренерская)
        self.assertEqual(self.db.query(Athlete).get(s1.id).club_id, club.id)

    def test_admin_show_coach_keeps_detached(self):
        club = self._club()
        coach = self._coach(club_id=club.id)
        self._athlete(club_id=club.id, coach_id=coach.id)

        admin_update_coach(coach.id, CoachUpdate(is_hidden=True), self.db, None)
        admin_update_coach(coach.id, CoachUpdate(is_hidden=False), self.db, None)

        coach = self.db.query(Coach).get(coach.id)
        self.assertFalse(coach.is_hidden)
        # «Показать» ничего не восстанавливает — как у спортсменов
        self.assertIsNone(coach.club_id)
        self.assertEqual(
            self.db.query(Athlete).filter(Athlete.coach_id == coach.id).count(), 0
        )

    def test_admin_delete_coach_releases_students(self):
        club = self._club()
        coach = self._coach(club_id=club.id)
        s1 = self._athlete(club_id=club.id, coach_id=coach.id)

        res = admin_delete_coach(coach.id, self.db, None)
        self.assertEqual(res["status"], "deleted")
        self.assertIsNone(self.db.query(Athlete).get(s1.id).coach_id)
        self.assertEqual(self.db.query(Athlete).get(s1.id).club_id, club.id)

    def test_sync_hide_coach_releases_students_and_leaves_club(self):
        club = self._club()
        coach = self._coach(club_id=club.id)
        s1 = self._athlete(club_id=club.id, coach_id=coach.id)

        res = sync_update_coach(coach.id, CoachSyncUpdate(is_hidden=True), self.db, True)
        self.assertEqual(res["status"], "ok")
        coach = self.db.query(Coach).get(coach.id)
        self.assertTrue(coach.is_hidden)
        self.assertIsNone(coach.club_id)
        self.assertIsNone(self.db.query(Athlete).get(s1.id).coach_id)

    def test_sync_delete_coach_releases_students(self):
        club = self._club()
        coach = self._coach(club_id=club.id)
        s1 = self._athlete(club_id=club.id, coach_id=coach.id)

        res = sync_delete_coach(coach.id, self.db, True)
        self.assertEqual(res["status"], "deleted")
        self.assertIsNone(self.db.query(Athlete).get(s1.id).coach_id)

    def test_public_coaches_exclude_hidden(self):
        club = self._club()
        coach = self._coach(club_id=club.id)
        admin_update_coach(coach.id, CoachUpdate(is_hidden=True), self.db, None)

        page = public_list_coaches(name=None, club_id=None, page=1, page_size=50, db=self.db)
        self.assertNotIn(coach.id, [c.id for c in page.items])
        self.assertEqual(page.total, 0)

        with self.assertRaises(HTTPException) as ctx:
            public_get_coach(coach.id, self.db)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_public_club_members_exclude_hidden_coach(self):
        club = self._club()
        coach = self._coach(club_id=club.id, full_name="Скрытый Тренер")
        self._coach(club_id=club.id, full_name="Видимый Тренер")
        admin_update_coach(coach.id, CoachUpdate(is_hidden=True), self.db, None)

        detail = public_get_club(club.id, self.db)
        self.assertEqual(detail.coaches_count, 1)
        self.assertNotIn(coach.id, [c.id for c in detail.coaches])

    def test_admin_list_includes_hidden_coaches(self):
        club = self._club()
        coach = self._coach(club_id=club.id)
        admin_update_coach(coach.id, CoachUpdate(is_hidden=True), self.db, None)

        rows = list_coaches_admin(page=1, page_size=200, db=self.db, _=None)
        item = next(c for c in rows.items if c.id == coach.id)
        self.assertTrue(item.is_hidden)

    def test_sync_changes_include_hidden_coach(self):
        coach = self._coach()
        admin_update_coach(coach.id, CoachUpdate(is_hidden=True), self.db, None)

        changes = get_coach_changes(None, self.db, True)
        item = next(c for c in changes.updated if c.id == coach.id)
        self.assertTrue(item.is_hidden)

    def test_sync_hide_coach_then_delete_idempotent(self):
        """Скрытый тренер удаляется без ошибок (ученики уже отпущены)."""
        coach = self._coach()
        s1 = self._athlete(coach_id=coach.id)
        admin_update_coach(coach.id, CoachUpdate(is_hidden=True), self.db, None)
        res = admin_delete_coach(coach.id, self.db, None)
        self.assertEqual(res["status"], "deleted")
        self.assertIsNone(self.db.query(Athlete).get(s1.id).coach_id)

    # ═══ СПОРТСМЕН ══════════════════════════════════════════════
    def test_admin_hide_athlete_detaches_and_penalizes_club(self):
        club = self._club()
        coach = self._coach()
        a = self._athlete(club_id=club.id, coach_id=coach.id)
        self._give_club_points(club.id, a.id)

        admin_update_athlete(a.id, AthleteUpdate(is_hidden=True), self.db, None)

        a = self.db.query(Athlete).get(a.id)
        self.assertTrue(a.is_hidden)
        self.assertIsNone(a.club_id)
        self.assertIsNone(a.coach_id)
        self.assertFalse(a.club_active)
        self.assertIsNone(a.join_club_date)
        self.assertEqual(cr.get_club_rating(self.db, club.id), 90)
        self.assertEqual(_rating_history(self.db, club.id, "ATHLETE_REMOVED"), 1)

    def test_admin_hide_athlete_idempotent_penalty(self):
        club = self._club()
        a = self._athlete(club_id=club.id)
        self._give_club_points(club.id, a.id)

        admin_update_athlete(a.id, AthleteUpdate(is_hidden=True), self.db, None)
        admin_update_athlete(a.id, AthleteUpdate(is_hidden=False), self.db, None)
        # второй раз скрываем уже без клуба — штраф НЕ задваивается
        admin_update_athlete(a.id, AthleteUpdate(is_hidden=True), self.db, None)

        self.assertEqual(cr.get_club_rating(self.db, club.id), 90)
        self.assertEqual(_rating_history(self.db, club.id, "ATHLETE_REMOVED"), 1)

    def test_admin_hard_delete_athlete_penalizes_club(self):
        club = self._club()
        a = self._athlete(club_id=club.id)
        self._give_club_points(club.id, a.id)

        res = admin_delete_athlete(a.id, self.db, None)
        self.assertEqual(res["status"], "deleted")
        self.assertIsNone(self.db.query(Athlete).get(a.id))
        self.assertEqual(cr.get_club_rating(self.db, club.id), 90)
        self.assertEqual(_rating_history(self.db, club.id, "ATHLETE_REMOVED"), 1)

    def test_admin_delete_athlete_with_participations_hides_and_detaches(self):
        club = self._club()
        coach = self._coach()
        a = self._athlete(club_id=club.id, coach_id=coach.id)
        self._participant(a.id)
        self._give_club_points(club.id, a.id)

        res = admin_delete_athlete(a.id, self.db, None)
        self.assertEqual(res["status"], "hidden")
        a = self.db.query(Athlete).get(a.id)
        self.assertTrue(a.is_hidden)
        self.assertIsNone(a.club_id)
        self.assertIsNone(a.coach_id)
        self.assertEqual(cr.get_club_rating(self.db, club.id), 90)

    def test_sync_hide_athlete_detaches_and_penalizes(self):
        club = self._club()
        coach = self._coach()
        a = self._athlete(club_id=club.id, coach_id=coach.id)
        self._give_club_points(club.id, a.id)

        sync_update_athlete(a.id, AthleteSyncUpdate(is_hidden=True), self.db, True)

        a = self.db.query(Athlete).get(a.id)
        self.assertTrue(a.is_hidden)
        self.assertIsNone(a.club_id)
        self.assertIsNone(a.coach_id)
        self.assertEqual(cr.get_club_rating(self.db, club.id), 90)

    def test_sync_delete_athlete_penalizes_club(self):
        club = self._club()
        a = self._athlete(club_id=club.id)
        self._give_club_points(club.id, a.id)

        sync_delete_athlete(a.id, self.db, True)
        self.assertEqual(cr.get_club_rating(self.db, club.id), 90)

    def test_sync_delete_athlete_with_participations_hides_and_detaches(self):
        club = self._club()
        coach = self._coach()
        a = self._athlete(club_id=club.id, coach_id=coach.id)
        self._participant(a.id)
        self._give_club_points(club.id, a.id)

        res = sync_delete_athlete(a.id, self.db, True)
        self.assertEqual(res["status"], "hidden")
        a = self.db.query(Athlete).get(a.id)
        self.assertTrue(a.is_hidden)
        self.assertIsNone(a.club_id)
        self.assertIsNone(a.coach_id)

    def test_sync_athlete_changes_report_detached_hidden(self):
        club = self._club()
        coach = self._coach()
        a = self._athlete(club_id=club.id, coach_id=coach.id)
        admin_update_athlete(a.id, AthleteUpdate(is_hidden=True), self.db, None)

        changes = get_athlete_changes(None, self.db, True)
        item = next(x for x in changes.updated if x.id == a.id)
        self.assertTrue(item.is_hidden)
        self.assertIsNone(item.club_name)
        self.assertIsNone(item.coach_name)

    def test_unhide_then_reassign_reattaches_athlete(self):
        club = self._club()
        a = self._athlete(club_id=club.id)
        admin_update_athlete(a.id, AthleteUpdate(is_hidden=True), self.db, None)
        admin_update_athlete(a.id, AthleteUpdate(is_hidden=False), self.db, None)

        # возвращаем в тот же клуб — клубная привязка снова работает
        admin_update_athlete(a.id, AthleteUpdate(club_id=club.id), self.db, None)
        a = self.db.query(Athlete).get(a.id)
        self.assertEqual(a.club_id, club.id)
        self.assertIsNotNone(a.join_club_date)
        self.assertFalse(a.is_hidden)

    def test_admin_athlete_list_includes_hidden(self):
        club = self._club()
        a = self._athlete(club_id=club.id)
        admin_update_athlete(a.id, AthleteUpdate(is_hidden=True), self.db, None)

        rows = list_athletes_admin(name=None, db=self.db, _=None)
        item = next(x for x in rows if x.id == a.id)
        self.assertTrue(item.is_hidden)


if __name__ == "__main__":
    unittest.main()
