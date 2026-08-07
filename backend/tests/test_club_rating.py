"""Тесты системы рейтинга клубов.

Запуск:  backend/venv/Scripts/python -m unittest tests.test_club_rating -v

Использует отдельную in-memory SQLite базу с теми же ORM-моделями, что и
продакшн (app.db.models), поэтому проверяет именно боевую логику сервиса
app/services/club_rating.py без реальной БД.
"""
from __future__ import annotations

import os
import unittest
from datetime import date, timedelta

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DESKTOP_SYNC_TOKEN", "test-sync-token")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
import app.db.models  # noqa: F401  (регистрирует все модели в Base.metadata)
from app.db.models.athletes import Athlete
from app.db.models.categories import Category
from app.db.models.club_rating import ClubRating, ClubRatingHistory
from app.db.models.clubs import Club
from app.db.models.competitions import Competition, CompetitionParticipant
from app.db.models.dvoeborie_override import DvoeborieOverride
from app.db.models.matches import Match
from app.db.models.results import Result
from app.db.models.statistics import AthleteStatistic
from app.services import club_rating as cr


def _make_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class ClubRatingServiceTest(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.club_a = Club(name="Клуб А")
        self.club_b = Club(name="Клуб Б")
        self.db.add_all([self.club_a, self.club_b])
        self.db.flush()

        self.ath_a = self._ath("Иван Иванов", self.club_a)
        self.ath_b = self._ath("Пётр Петров", self.club_b)
        self.ath_free = self._ath("Сидор Сидоров", None)
        self.db.commit()

    def _ath(self, name, club):
        a = Athlete(full_name=name, club_id=club.id if club else None)
        self.db.add(a)
        self.db.flush()
        self.db.add(AthleteStatistic(athlete_id=a.id))
        return a

    def _competition(self, status="completed"):
        c = Competition(name="Чемпионат области", date=date(2026, 1, 15), status=status)
        self.db.add(c)
        self.db.flush()
        return c

    def tearDown(self):
        self.db.close()

    # ── базовые правила ─────────────────────────────────────────

    def test_new_club_starts_at_zero(self):
        self.assertEqual(cr.get_club_rating(self.db, self.club_a.id), 0)

    def test_add_points_increments_rating(self):
        r = cr.add_points(self.db, self.club_a.id, self.ath_a.id, None, 5, "X", "test")
        self.assertTrue(r["applied"])
        self.assertEqual(cr.get_club_rating(self.db, self.club_a.id), 5)

    def test_add_points_is_idempotent(self):
        cr.add_points(self.db, self.club_a.id, self.ath_a.id, None, 5, "X", "test")
        r = cr.add_points(self.db, self.club_a.id, self.ath_a.id, None, 5, "X", "test")
        self.assertFalse(r["applied"])
        self.assertEqual(cr.get_club_rating(self.db, self.club_a.id), 5)
        self.assertEqual(len(cr.get_club_rating_history(self.db, self.club_a.id)), 1)

    def test_rating_never_negative_but_history_keeps_real_value(self):
        cr.add_points(self.db, self.club_a.id, self.ath_a.id, None, 3, "BASE", "тест")
        cr.add_points(self.db, self.club_a.id, self.ath_a.id, None, -10, "PEN", "штраф")
        self.assertEqual(cr.get_club_rating(self.db, self.club_a.id), 0)
        history = cr.get_club_rating_history(self.db, self.club_a.id)
        self.assertIn(-10, [h.points for h in history])
        # clubs.rating_points синхронизирован
        self.db.refresh(self.club_a)
        self.assertEqual(self.club_a.rating_points, 0)

    # ── удаление спортсмена из клуба ────────────────────────────

    def test_athlete_removed_penalty(self):
        cr.apply_athlete_removed(self.db, self.ath_a.id, self.club_a.id)
        self.assertEqual(cr.get_club_rating(self.db, self.club_a.id), 0)  # 0-10 -> 0
        history = cr.get_club_rating_history(self.db, self.club_a.id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].points, -10)
        self.assertEqual(history[0].reason, cr.REASON_ATHLETE_REMOVED)

    # ── неактивность ────────────────────────────────────────────

    def test_inactive_penalty_applied_once(self):
        self.ath_a.club_active = True
        self.ath_a.next_inactive_date = date.today() - timedelta(days=1)
        self.db.commit()

        count = cr.check_inactive_athletes(self.db)
        self.assertEqual(count, 1)
        self.assertEqual(cr.get_club_rating(self.db, self.club_a.id), 0)  # -5 -> 0

        self.db.refresh(self.ath_a)
        self.assertFalse(self.ath_a.club_active)
        self.assertIsNone(self.ath_a.next_inactive_date)

        # повторная проверка: спортсмен больше не в выборке, штраф один раз
        self.assertEqual(cr.check_inactive_athletes(self.db), 0)
        history = cr.get_club_rating_history(self.db, self.club_a.id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].reason, cr.REASON_INACTIVITY)

    def test_active_athlete_not_penalized(self):
        self.ath_a.club_active = True
        self.ath_a.next_inactive_date = date.today() + timedelta(days=10)
        self.db.commit()
        self.assertEqual(cr.check_inactive_athletes(self.db), 0)

    # ── участие / первое выступление ────────────────────────────

    def _participant(self, competition, category, athlete, club_name):
        p = CompetitionParticipant(
            competition_id=competition.id,
            category_id=category.id,
            athlete_id=athlete.id,
            club_at_event=club_name,
        )
        self.db.add(p)
        self.db.flush()
        return p

    def test_first_participation_gives_plus5_and_activates(self):
        comp = self._competition()
        cat = Category(competition_id=comp.id, name="80 кг", hand="Обе")
        self.db.add(cat)
        self.db.flush()
        p = self._participant(comp, cat, self.ath_a, "Клуб А")
        # нет ни одного завершённого матча — категория с одним участником
        self.db.commit()

        res = cr.finalize_competition(self.db, comp)
        self.assertEqual(res["status"], "ok")

        self.assertEqual(cr.get_club_rating(self.db, self.club_a.id), 5)
        self.db.refresh(self.ath_a)
        self.assertTrue(self.ath_a.club_active)
        self.assertEqual(self.ath_a.last_competition_date, comp.date)
        self.assertEqual(
            self.ath_a.next_inactive_date,
            cr.add_months(comp.date, cr.INACTIVE_MONTHS),
        )
        # join_club_date проставился автоматически
        self.assertIsNotNone(self.ath_a.join_club_date)

    def test_repeat_participation_no_extra_points(self):
        comp = self._competition()
        cat = Category(competition_id=comp.id, name="80 кг", hand="Обе")
        self.db.add(cat)
        self.db.flush()
        p = self._participant(comp, cat, self.ath_a, "Клуб А")
        self.db.commit()
        cr.finalize_competition(self.db, comp)

        # повторный вызов — ничего не задваивается (второй раз без матчей)
        cr.finalize_competition(self.db, comp)
        self.assertEqual(cr.get_club_rating(self.db, self.club_a.id), 5)

        # второй турнир — спортсмен уже активен, +5 не начисляется
        comp2 = self._competition()
        cat2 = Category(competition_id=comp2.id, name="80 кг", hand="Обе")
        self.db.add(cat2)
        self.db.flush()
        p2 = self._participant(comp2, cat2, self.ath_a, "Клуб А")
        self.db.commit()
        cr.finalize_competition(self.db, comp2)
        self.assertEqual(cr.get_club_rating(self.db, self.club_a.id), 5)

    # ── места (1-2-3) по матчам ─────────────────────────────────

    def test_place_points_from_bracket(self):
        comp = self._competition()
        cat = Category(competition_id=comp.id, name="80 кг", hand="Обе")
        self.db.add(cat)
        self.db.flush()

        p1 = self._participant(comp, cat, self.ath_a, "Клуб А")
        p2 = self._participant(comp, cat, self.ath_b, "Клуб Б")
        self.db.flush()

        # финал: победа спортсмена из клуба А над спортсменом клуба Б
        final = Match(
            competition_id=comp.id,
            category_id=cat.id,
            hand="Правая",
            bracket="final",
            status="done",
            p1_id=p1.id,
            p2_id=p2.id,
            winner_id=p1.id,
        )
        self.db.add(final)
        self.db.commit()

        res = cr.finalize_competition(self.db, comp)
        self.assertEqual(res["place_records"], 2)

        # 1 место (+10) + первое участие (+5) = 15 клубу А
        self.assertEqual(cr.get_club_rating(self.db, self.club_a.id), 15)
        # 2 место (+6) + первое участие (+5) = 11 клубу Б
        self.assertEqual(cr.get_club_rating(self.db, self.club_b.id), 11)

        result_a = (
            self.db.query(Result)
            .filter(Result.competition_participant_id == p1.id)
            .first()
        )
        self.assertEqual(result_a.place, 1)
        self.assertEqual(result_a.medal, "gold")

    def test_place_points_only_for_top3(self):
        comp = self._competition()
        cat = Category(competition_id=comp.id, name="80 кг", hand="Обе")
        self.db.add(cat)
        self.db.flush()

        p1 = self._participant(comp, cat, self.ath_a, "Клуб А")
        p2 = self._participant(comp, cat, self.ath_b, "Клуб Б")
        # третий спортсмен без клуба — места не влияют на клубы
        ath_c = self._ath("Кирилл Кириллов", None)
        p3 = self._participant(comp, cat, ath_c, None)
        self.db.flush()

        # финал А над Б + матч за 3 место Б над C
        self.db.add(Match(
            competition_id=comp.id, category_id=cat.id, hand="Правая",
            bracket="final", status="done", p1_id=p1.id, p2_id=p2.id, winner_id=p1.id,
        ))
        self.db.add(Match(
            competition_id=comp.id, category_id=cat.id, hand="Правая",
            bracket="losers", status="done", p1_id=p2.id, p2_id=p3.id, winner_id=p2.id,
        ))
        self.db.commit()

        cr.finalize_competition(self.db, comp)
        # А: 1 место 10 + участие 5 = 15; Б: 2 место 6 + участие 5 = 11
        self.assertEqual(cr.get_club_rating(self.db, self.club_a.id), 15)
        self.assertEqual(cr.get_club_rating(self.db, self.club_b.id), 11)

    def test_athlete_without_club_no_points(self):
        comp = self._competition()
        cat = Category(competition_id=comp.id, name="80 кг", hand="Обе")
        self.db.add(cat)
        self.db.flush()
        self._participant(comp, cat, self.ath_free, None)
        self.db.commit()
        cr.finalize_competition(self.db, comp)
        self.assertEqual(cr.get_club_rating(self.db, self.club_a.id), 0)
        self.assertEqual(cr.get_club_rating(self.db, self.club_b.id), 0)
        self.db.refresh(self.ath_free)
        self.assertTrue(self.ath_free.club_active)  # участие учтено в активности

    # ── вспомогательные ─────────────────────────────────────────

    def test_add_months(self):
        self.assertEqual(cr.add_months(date(2026, 1, 15), 6), date(2026, 7, 15))
        self.assertEqual(cr.add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(cr.add_months(date(2025, 12, 31), 1), date(2026, 1, 31))

    def test_recalc_from_history(self):
        cr.add_points(self.db, self.club_a.id, self.ath_a.id, None, 5, "X", "a")
        cr.add_points(self.db, self.club_a.id, self.ath_a.id, None, -10, "Y", "b")
        self.assertEqual(cr.get_club_rating(self.db, self.club_a.id), 0)
        # история: 5 + (-10) = -5, но аккумулятор зажимает в 0.
        # Пересчёт из истории так же даёт 0.
        self.assertEqual(cr.recalc_club_rating_from_history(self.db, self.club_a.id), 0)


class DvoeborieTiebreakTest(unittest.TestCase):
    """Тай-брейк двоеборья: при равных очках выше спортсмен с меньшим весом;
    при равных очках И весе место делится, если жюри не выбрало победителя
    (DvoeborieOverride.manual_rank)."""

    def setUp(self):
        self.db = _make_session()
        self.comp = Competition(name="Ч", date=date(2026, 1, 15), status="completed")
        self.db.add(self.comp)
        self.db.flush()
        self.cat = Category(competition_id=self.comp.id, name="55 кг", hand="Обе")
        self.db.add(self.cat)
        self.db.flush()
        self.a = self._part("А", weight=55.0)
        self.b = self._part("Б", weight=44.0)

    def _part(self, name, weight):
        athlete = Athlete(full_name=name)
        self.db.add(athlete)
        self.db.flush()
        self.db.add(AthleteStatistic(athlete_id=athlete.id))
        p = CompetitionParticipant(
            competition_id=self.comp.id, category_id=self.cat.id,
            athlete_id=athlete.id, weight_at_event=weight,
        )
        self.db.add(p)
        self.db.flush()
        return p

    def _final(self, hand, winner, loser):
        self.db.add(Match(
            competition_id=self.comp.id, category_id=self.cat.id, hand=hand,
            bracket="winners", stage=0, match_order=0, status="done",
            p1_id=winner.id, p2_id=loser.id, winner_id=winner.id,
        ))
        self.db.flush()

    def _standings(self):
        return cr._category_standings(self.db, self.comp, self.cat)

    def test_lighter_weight_wins_tie(self):
        # правая: А 1-е, Б 2-е; левая: Б 1-е, А 2-е → у обоих по 17 очков.
        self._final("Правая", self.a, self.b)
        self._final("Левая", self.b, self.a)
        self.db.commit()
        rows = {r["participant_id"]: r for r in self._standings()}
        # вес: Б(44) легче А(55) → Б выше
        self.assertEqual(rows[self.b.id]["place"], 1)
        self.assertEqual(rows[self.a.id]["place"], 2)

    def test_equal_weight_shares_place(self):
        self.a.weight_at_event = 44.0
        self.db.commit()
        self._final("Правая", self.a, self.b)
        self._final("Левая", self.b, self.a)
        self.db.commit()
        rows = {r["participant_id"]: r for r in self._standings()}
        self.assertEqual(rows[self.a.id]["place"], rows[self.b.id]["place"])
        self.assertEqual(rows[self.a.id]["place"], 1)

    def test_manual_override_breaks_tie(self):
        self.a.weight_at_event = 44.0
        self.db.commit()
        self._final("Правая", self.a, self.b)
        self._final("Левая", self.b, self.a)
        self.db.add(DvoeborieOverride(
            competition_id=self.comp.id, category_id=self.cat.id,
            participant_id=self.a.id, manual_rank=1,
        ))
        self.db.commit()
        rows = {r["participant_id"]: r for r in self._standings()}
        # жюри выбрало А победителем → А 1-е, Б 2-е
        self.assertEqual(rows[self.a.id]["place"], 1)
        self.assertEqual(rows[self.b.id]["place"], 2)

    def tearDown(self):
        self.db.close()


if __name__ == "__main__":
    unittest.main()
