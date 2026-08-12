"""Стресс-тесты рейтинговой системы клубов (desktop club_rating).

Прогоняют полный конвейер «турнир → сетка → награждение» на больших
данных через настоящие движки (DoubleEliminationEngine /
SingleEliminationEngine) и проверяют инварианты рейтинга:

- согласованность: rating клуба всегда == max(0, SUM(points)) его
  истории (recalc из истории не меняет значение);
- уникальность журнала: нет двух записей (club, athlete, tournament,
  reason, description) — начисление идемпотентно;
- rating никогда не отрицательный;
- места 1-3 получают ровно +10/+6/+3, 4+ — ничего;
- первое участие (+5) начисляется один раз на спортсмена;
- детерминизм: одинаковые турниры дают одинаковый рейтинг;
- цепочка из N турниров, неактивность (-5), удаление из клуба (-10);
- перенос .armwrestling сохраняет рейтинг (награждение на «втором
  ноутбуке» даёт те же баллы);
- двоеборье (обе руки) и bye-матчи (нечётные сетки);
- производительность: 1000 спортсменов в пределах разумного времени.
"""

import os
import shutil
import tempfile
import time
import unittest
from datetime import date

import armwrestling_tournament as app
from club_rating import (FIRST_PARTICIPATION_POINTS, PLACE_POINTS,
                         REASON_ATHLETE_REMOVED, REASON_FIRST_PARTICIPATION,
                         REASON_INACTIVITY, REASON_PLACE, add_points,
                         apply_athlete_removed, check_inactive_athletes,
                         finalize_competition, get_club_rating,
                         get_club_rating_history, recalc_club_rating_from_history)
from tests.export_import.helpers import Laptop2, _NoSync  # noqa: E402

from transfer.exporter import export_competition  # noqa: E402
from transfer.importer import import_competition  # noqa: E402


class _SyncStub(_NoSync):
    force_queue = False
    enabled = False

    def on_bracket_reset(self, category_id, hand, local_mids):
        pass

    def flush_pending(self):
        pass


HAND = "Правая"
DATE = "10.08.2026"


class RatingStressBase(unittest.TestCase):
    """Турнир с реестром клубов/спортсменов и честными сетками."""

    n_clubs = 16
    n_athletes = 512

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="armw_rating_stress_")
        app.sync_manager = _SyncStub()
        app.DB_PATH = os.path.join(self.tmp, "rating.db")
        app.PHOTOS_DIR = os.path.join(self.tmp, "photos")
        os.makedirs(app.PHOTOS_DIR, exist_ok=True)
        self.db = app.Database()
        self.clubs = []
        for i in range(self.n_clubs):
            cur = self.db.conn.execute(
                "INSERT INTO clubs (name, city) VALUES (?, ?)",
                (f"Клуб {i}", f"Город {i % 7}"))
            self.clubs.append(cur.lastrowid)
        self.club_names = {cid: f"Клуб {i}" for i, cid in enumerate(self.clubs)}
        self.athletes = []
        for i in range(self.n_athletes):
            cid = self.clubs[i % self.n_clubs]
            aid = self.db.add_athlete(
                f"Имя{i}", f"Фамилия{i}", "2000-01-01", "M",
                club_id=cid)
            self.athletes.append((aid, cid))
        self.db.conn.commit()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── строительство турнира ───────────────────────────────────
    def _play_until_done(self, engine, cid, hand):
        steps = 0
        while True:
            ms = self.db.get_matches(cid, hand)
            ready = [m for m in ms if m["status"] == "pending"
                     and m["p1_id"] and m["p2_id"]]
            if not ready:
                break
            m = ready[0]
            engine.advance_winner(m["id"], m["p1_id"])
            steps += 1
            self.assertLess(steps, 500000, "сетка не сходится")

    def _build_tournament(self, name, cat_specs, hand=HAND,
                          engine_cls=app.DoubleEliminationEngine,
                          athlete_pool=None, finish=True):
        """cat_specs: список (имя, вес, число участников). Участники
        берутся по кругу из athlete_pool (по умолчанию все)."""
        pool = athlete_pool if athlete_pool is not None else self.athletes
        tid = self.db.create_tournament(name, DATE, "Stress City",
                                        bracket_system="double")
        cursor = 0
        for cat_name, weight, count in cat_specs:
            cid = self.db.add_category(tid, cat_name, weight, hand)
            pids = []
            for _ in range(count):
                aid, club_id = pool[cursor % len(pool)]
                cursor += 1
                pid = self.db.add_participant(
                    tid, f"Имя{aid} Фамилия{aid}", weight - 5,
                    self.club_names[club_id], cid, hand=hand, athlete_id=aid)
                pids.append(pid)
            engine = engine_cls(self.db)
            engine.generate_bracket(tid, cid, hand, pids)
            self._play_until_done(engine, cid, hand)
        if finish:
            self.db.finish_tournament(tid)
        return tid

    # ── инварианты ──────────────────────────────────────────────
    def _assert_history_unique(self):
        dup = self.db.conn.execute(
            "SELECT club_id, athlete_id, tournament_id, reason, description, "
            "COUNT(*) AS n FROM club_rating_history "
            "GROUP BY club_id, athlete_id, tournament_id, reason, description "
            "HAVING n > 1").fetchall()
        self.assertEqual(dup, [], f"дубли в истории рейтинга: {dup}")

    def _assert_ratings_consistent(self):
        """rating клуба == max(0, сумма истории); пересчёт не меняет."""
        for club_id in self.clubs:
            stored = get_club_rating(self.db.conn, club_id)
            self.assertGreaterEqual(stored, 0,
                                    f"клуб {club_id} с отрицательным "
                                    f"рейтингом {stored}")
            total = self.db.conn.execute(
                "SELECT COALESCE(SUM(points), 0) AS s FROM "
                "club_rating_history WHERE club_id=?", (club_id,)).fetchone()[0]
            expected = max(0, total)
            self.assertEqual(stored, expected,
                             f"клуб {club_id}: rating {stored} != "
                             f"история {expected}")
            recalc = recalc_club_rating_from_history(self.db.conn, club_id)
            self.assertEqual(recalc, stored,
                             f"клуб {club_id}: recalc изменил рейтинг")

    def _assert_history_empty(self):
        n = self.db.conn.execute(
            "SELECT COUNT(*) FROM club_rating_history").fetchone()[0]
        self.assertEqual(n, 0)


class TestRatingScale(RatingStressBase):
    """512 спортсменов, 8 категорий по 64 — полный конвейер."""

    def test_full_pipeline_512(self):
        tid = self._build_tournament(
            "Большой турнир",
            [(f"Категория {i}", 50 + i * 5, 64) for i in range(8)])
        res = finalize_competition(self.db.conn, tid)
        self.assertEqual(res["status"], "ok")

        # Каждый участник (все 512) впервые выступает за клуб: +5.
        n_first = self.db.conn.execute(
            "SELECT COUNT(*) FROM club_rating_history WHERE reason=?",
            (REASON_FIRST_PARTICIPATION,)).fetchone()[0]
        self.assertEqual(n_first, 512)
        # По 3 призёра на категорию: 8 × 3 записей PLACE.
        n_place = self.db.conn.execute(
            "SELECT COUNT(*) FROM club_rating_history WHERE reason=?",
            (REASON_PLACE,)).fetchone()[0]
        self.assertEqual(n_place, 24)
        self._assert_history_unique()
        self._assert_ratings_consistent()

    def test_place_points_only_top3(self):
        tid = self._build_tournament(
            "Призовой", [("A", 60, 32), ("B", 70, 32)])
        finalize_competition(self.db.conn, tid)
        for place, pts in PLACE_POINTS.items():
            rows = self.db.conn.execute(
                "SELECT description FROM club_rating_history "
                "WHERE reason=? AND points=?", (REASON_PLACE, pts)).fetchall()
            self.assertEqual(len(rows), 2,
                             f"мест {place} должно быть ровно 2 категории, "
                             f"нашлось {len(rows)}: {rows}")
        no_extra = self.db.conn.execute(
            "SELECT COUNT(*) FROM club_rating_history WHERE reason=? "
            "AND points NOT IN (10, 6, 3)", (REASON_PLACE,)).fetchone()[0]
        self.assertEqual(no_extra, 0)
        self._assert_ratings_consistent()


class TestRatingIdempotenceAndDeterminism(RatingStressBase):
    def test_finalize_twice_is_noop(self):
        tid = self._build_tournament(
            "Двойной", [(f"К{i}", 55 + i, 48) for i in range(4)])
        r1 = finalize_competition(self.db.conn, tid)
        h1 = get_club_rating_history(self.db.conn, self.clubs[0])
        r2 = finalize_competition(self.db.conn, tid)
        h2 = get_club_rating_history(self.db.conn, self.clubs[0])
        self.assertEqual(r1["status"], "ok")
        self.assertEqual(r2["status"], "ok")
        self.assertEqual(h1, h2, "повторный finalize задвоил начисления")
        self._assert_history_unique()
        self._assert_ratings_consistent()

    def test_same_tournaments_same_ratings(self):
        def run():
            tid = self._build_tournament(
                "Детерминизм", [("A", 65, 64), ("B", 75, 64)])
            finalize_competition(self.db.conn, tid)
            return {cid: get_club_rating(self.db.conn, cid)
                    for cid in self.clubs}
        # Первый прогон на «чистом» реестре.
        ratings1 = run()
        # Сбрасываем рейтинг и историю, повторяем точно такой же турнир.
        self.db.conn.execute("DELETE FROM club_rating_history")
        self.db.conn.execute("DELETE FROM club_rating")
        self.db.conn.execute(
            "UPDATE athletes SET club_active=0, last_competition_date=NULL, "
            "next_inactive_date=NULL")
        ratings2 = run()
        self.assertEqual(ratings1, ratings2, "рейтинг недетерминирован")

    def test_no_second_first_participation(self):
        tid1 = self._build_tournament("Первый", [("A", 65, 128)])
        finalize_competition(self.db.conn, tid1)
        first_after_1 = self.db.conn.execute(
            "SELECT COUNT(*) FROM club_rating_history WHERE reason=?",
            (REASON_FIRST_PARTICIPATION,)).fetchone()[0]
        self.assertEqual(first_after_1, 128)

        tid2 = self._build_tournament("Второй", [("A", 65, 128)])
        finalize_competition(self.db.conn, tid2)
        first_after_2 = self.db.conn.execute(
            "SELECT COUNT(*) FROM club_rating_history WHERE reason=?",
            (REASON_FIRST_PARTICIPATION,)).fetchone()[0]
        self.assertEqual(first_after_2, 128,
                         "+5 за «первое участие» начислен повторно")
        self._assert_ratings_consistent()

    def test_chain_of_five_tournaments(self):
        for i in range(5):
            tid = self._build_tournament(
                f"Серия {i}",
                [(f"Кат {i}-{j}", 50 + (i + j) * 3 % 40, 32)
                 for j in range(4)])
            finalize_competition(self.db.conn, tid)
        self._assert_history_unique()
        self._assert_ratings_consistent()


class TestRatingPenalties(RatingStressBase):
    n_clubs = 1
    n_athletes = 300

    def test_inactivity_penalty_once(self):
        today = date(2026, 8, 12)
        self.db.conn.execute(
            "UPDATE athletes SET club_active=1, "
            "next_inactive_date='2026-08-01', last_competition_date='2025-01-01'")
        self.db.conn.commit()
        n1 = check_inactive_athletes(self.db.conn, today=today)
        self.assertEqual(n1, self.n_athletes,
                         "все просроченные спортсмены должны получить -5")
        n_pen = self.db.conn.execute(
            "SELECT COUNT(*) FROM club_rating_history WHERE reason=?",
            (REASON_INACTIVITY,)).fetchone()[0]
        self.assertEqual(n_pen, self.n_athletes)
        n2 = check_inactive_athletes(self.db.conn, today=today)
        self.assertEqual(n2, 0, "повторный штраф за неактивность")
        self._assert_history_unique()
        self._assert_ratings_consistent()

    def test_removal_penalty_idempotent(self):
        club_id = self.clubs[0]
        for aid, cid in self.athletes[:100]:
            self.assertEqual(cid, club_id)
            r = add_points(self.db.conn, club_id, aid, None, 50,
                           "TEST", "начисление до удаления")
            self.assertTrue(r["applied"])
        for aid, cid in self.athletes[:100]:
            apply_athlete_removed(self.db.conn, aid, cid)
            apply_athlete_removed(self.db.conn, aid, cid)
        n_rem = self.db.conn.execute(
            "SELECT COUNT(*) FROM club_rating_history WHERE reason=?",
            (REASON_ATHLETE_REMOVED,)).fetchone()[0]
        self.assertEqual(n_rem, 100,
                         "повторный штраф за удаление спортсмена")
        # Баланс клуба: +5000 тестовых - 1000 штрафов = 4000.
        self.assertEqual(get_club_rating(self.db.conn, club_id), 4000)
        self._assert_history_unique()
        self._assert_ratings_consistent()


class TestRatingSpecialBrackets(RatingStressBase):
    n_athletes = 128

    def test_dvoeborie_both_hands(self):
        tid = self.db.create_tournament("Двоеборье", DATE, "X")
        cid = self.db.add_category(tid, "Обе руки", 75, "Обе")
        pids = []
        for i in range(32):
            aid, club_id = self.athletes[i % len(self.athletes)]
            pids.append(self.db.add_participant(
                tid, f"Имя{aid} Фамилия{aid}", 70,
                self.club_names[club_id], cid, hand="Обе", athlete_id=aid))
        for hand in ("Правая", "Левая"):
            engine = app.DoubleEliminationEngine(self.db)
            engine.generate_bracket(tid, cid, hand, pids)
            self._play_until_done(engine, cid, hand)
        self.db.finish_tournament(tid)
        res = finalize_competition(self.db.conn, tid)
        self.assertEqual(res["status"], "ok")
        n_place = self.db.conn.execute(
            "SELECT COUNT(*) FROM club_rating_history WHERE reason=?",
            (REASON_PLACE,)).fetchone()[0]
        self.assertEqual(n_place, 3,
                         "при двоеборье призёры определяются по сумме рук")
        self._assert_history_unique()
        self._assert_ratings_consistent()

    def test_odd_sizes_with_byes(self):
        tid = self.db.create_tournament("Нечётные", DATE, "X",
                                        bracket_system="single")
        engine_cls = app.SingleEliminationEngine
        for size in (3, 5, 17):
            cid = self.db.add_category(tid, f"К {size}", 60 + size, HAND)
            pids = []
            for i in range(size):
                aid, club_id = self.athletes[i % len(self.athletes)]
                pids.append(self.db.add_participant(
                    tid, f"Имя{aid} Фамилия{aid}", 55,
                    self.club_names[club_id], cid, hand=HAND,
                    athlete_id=aid))
            engine = engine_cls(self.db)
            engine.generate_bracket(tid, cid, HAND, pids)
            self._play_until_done(engine, cid, HAND)
        self.db.finish_tournament(tid)
        res = finalize_competition(self.db.conn, tid)
        self.assertEqual(res["status"], "ok")
        n_place = self.db.conn.execute(
            "SELECT COUNT(*) FROM club_rating_history WHERE reason=?",
            (REASON_PLACE,)).fetchone()[0]
        self.assertEqual(n_place, 9, "3 категории × 3 призёра")
        self._assert_history_unique()
        self._assert_ratings_consistent()

    def test_unfinished_tournament_skipped(self):
        tid = self._build_tournament("Незавершён", [("A", 60, 16)],
                                     finish=False)
        res = finalize_competition(self.db.conn, tid)
        self.assertEqual(res["status"], "skipped")
        self._assert_history_empty()


class TestRatingRoundtrip(RatingStressBase):
    n_athletes = 64

    def test_roundtrip_keeps_ratings(self):
        tid = self._build_tournament("Перенос", [("A", 60, 32),
                                                 ("B", 70, 32)])
        finalize_competition(self.db.conn, tid)
        src_ratings = {cid: get_club_rating(self.db.conn, cid)
                       for cid in self.clubs}

        dest = os.path.join(self.tmp, "t.armwrestling")
        export_competition(self.db.conn, None, tid, dest)
        laptop = Laptop2()
        try:
            import_competition(laptop.db.conn, None, dest,
                               photos_dir=app.PHOTOS_DIR)
            # На «втором ноутбуке» турнир ещё не награждён: финализируем —
            # рейтинги должны совпасть с исходными.
            imported_tid = laptop.db.conn.execute(
                "SELECT id FROM tournaments").fetchone()["id"]
            res = finalize_competition(laptop.db.conn, imported_tid)
            self.assertEqual(res["status"], "ok")
            for club_id in self.clubs:
                self.assertEqual(
                    get_club_rating(laptop.db.conn, club_id),
                    src_ratings[club_id],
                    f"клуб {club_id}: рейтинг разошёлся после переноса")
        finally:
            shutil.rmtree(laptop.tmp, ignore_errors=True)


class TestRatingPerformance(RatingStressBase):
    n_clubs = 20
    n_athletes = 1000

    def test_thousand_athletes_pipeline(self):
        t0 = time.time()
        tid = self._build_tournament(
            "Тысячник",
            [(f"К {i}", 45 + i * 5, 125) for i in range(8)])
        finalize_competition(self.db.conn, tid)
        elapsed = time.time() - t0
        self.assertLess(elapsed, 120,
                        f"1000 спортсменов за {elapsed:.1f}с — слишком "
                        "долго")
        self._assert_history_unique()
        self._assert_ratings_consistent()
        n_hist = self.db.conn.execute(
            "SELECT COUNT(*) FROM club_rating_history").fetchone()[0]
        self.assertEqual(n_hist, 1000 + 24,
                         f"история: 1000 участий + 24 призёра, "
                         f"а получилось {n_hist}")


if __name__ == "__main__":
    unittest.main()