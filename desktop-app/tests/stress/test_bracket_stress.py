"""Стресс-тесты сетки соревнования (bracket).

Проверяют настоящий движок из приложения (DoubleEliminationEngine /
SingleEliminationEngine + _run_batched_bracket_generation) на больших
данных:

- структурные инварианты при генерации для n = 2..256 участников
  (покрытие участников в 1-м раунде, bye только при нечётном n, все
  win_next/lose_next ссылки существуют и указывают на матчи той же
  категории/руки, нет циклов в winners-ветке, финалы на месте);
- полный прогон сетки до чемпиона (все матчи завершены, ровно один
  чемпион) для double и single на 64..256 участников;
- скорость генерации большой сетки (батчированный commit);
- сброс/перегенерация (clear_matches, поколения bracket_generations);
- несколько категорий одновременно — полная изоляция между ними;
- связка с экспортом/импортом: сетка с сыгранными матчами переносится
  на «второй ноутбук» побайтно идентично, прогон продолжается там.
"""

import os
import shutil
import time
import unittest

import armwrestling_tournament as app
from tests.export_import.helpers import Laptop2, _NoSync  # noqa: E402

from transfer.exporter import (export_competition,  # noqa: E402
                               validate_competition_integrity)
from transfer.importer import import_competition  # noqa: E402


class _SyncStub(_NoSync):
    """Заглушка sync_manager: сеть недоступна, всё локально. Нужны атрибуты,
    которые трогает _run_batched_bracket_generation и движки."""

    force_queue = False
    enabled = False

    def on_bracket_reset(self, category_id, hand, local_mids):
        pass

    def flush_pending(self):
        pass


HAND = "Правая"


class BracketFixture(unittest.TestCase):
    """Турнир с одной категорией и N участниками; движок настраивается
    подклассом (Double/Single)."""

    engine_cls = None
    bracket_system = "double"
    participants = 64

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="armw_bracket_stress_")
        app.sync_manager = _SyncStub()
        app.DB_PATH = os.path.join(self.tmp, "bracket.db")
        app.PHOTOS_DIR = os.path.join(self.tmp, "photos")
        os.makedirs(app.PHOTOS_DIR, exist_ok=True)
        self.db = app.Database()
        self.tid = self.db.create_tournament(
            "Bracket Stress 2026", "20.08.2026", "Bracket City",
            bracket_system=self.bracket_system)
        self.cat = self.db.add_category(self.tid, "80 кг", 80, HAND)
        self.pids = []
        for i in range(self.participants):
            self.pids.append(self.db.add_participant(
                self.tid, f"Боец {i}", 75 + i % 5, "Club", self.cat, HAND))
        self.engine = self.engine_cls(self.db)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── генерация и проверка ─────────────────────────────────────
    def _generate(self, n=None):
        pids = self.pids if n is None else self.pids[:n]
        self.engine.generate_bracket(self.tid, self.cat, HAND, pids)
        return self._matches()

    def _matches(self):
        return [dict(m) for m in self.db.get_matches(self.cat, HAND)]

    def _check_bracket(self, ms, n):
        """Структурные инварианты сетки."""
        by_id = {}
        for m in ms:
            self.assertNotIn(m["id"], by_id, "дубль id матча")
            by_id[m["id"]] = m
            self.assertEqual(m["category_id"], self.cat)
            self.assertEqual(m["hand"], HAND)
            self.assertIn(m["status"], ("pending", "waiting", "done", "bye"))
        self.assertEqual(len(ms), len(by_id))
        # 1-й раунд: каждый участник ровно один раз; bye только при
        # нечётном n и только один.
        round1 = [m for m in ms if m["bracket"] == "winners" and m["stage"] == 0]
        seen = []
        for m in round1:
            if m["p1_id"] is not None:
                seen.append(m["p1_id"])
            if m["p2_id"] is not None:
                seen.append(m["p2_id"])
        self.assertEqual(sorted(seen), sorted(self.pids[:n]))
        self.assertEqual(sum(1 for m in round1 if m["is_bye"]), n % 2)
        # Ссылки win_next/lose_next: существуют, той же категории/руки,
        # слот 1/2 (0 — спец-слот переигровки гранд-финала), не на себя.
        for m in ms:
            for col, slot in (("win_next_id", "win_next_slot"),
                              ("lose_next_id", "lose_next_slot")):
                nxt = m[col]
                if nxt is None:
                    continue
                self.assertIn(nxt, by_id, f"матч {m['id']}: ссылка {col} "
                                           f"на отсутствующий матч {nxt}")
                self.assertIn(m[slot], (0, 1, 2))
                t = by_id[nxt]
                self.assertEqual(t["category_id"], self.cat)
                self.assertEqual(t["hand"], HAND)
                self.assertNotEqual(nxt, m["id"], "матч ссылается сам на себя")
        # winners-ветка без циклов: цепочка от 1-го раунда по win_next
        # всегда доходит до терминального матча (у которого нет win_next).
        terminals = [m for m in ms if m["win_next_id"] is None]
        self.assertTrue(terminals, "нет терминальных матчей (финалов)")
        for m in round1:
            cur, visited = m, set()
            while cur["win_next_id"]:
                self.assertNotIn(cur["id"], visited,
                                 f"цикл winners-ветки у матча {cur['id']}")
                visited.add(cur["id"])
                cur = by_id[cur["win_next_id"]]
            self.assertIsNone(cur["win_next_id"],
                              f"winners-цепочка от {m['id']} не доходит "
                              "до терминального матча")
        # Каждый waiting-матч имеет источник (или это финал).
        for m in ms:
            if m["status"] != "waiting":
                continue
            if m["bracket"] == "final":
                continue
            sources = [s for s in ms
                       if s["win_next_id"] == m["id"]
                       or s["lose_next_id"] == m["id"]]
            self.assertTrue(sources,
                            f"waiting-матч {m['id']} без источников")

    def _play_through(self):
        """Играет всю сетку до конца: всегда побеждает p1. Возвращает
        (ходы, чемпион)."""
        steps = 0
        while True:
            ms = self._matches()
            ready = [m for m in ms
                     if m["status"] == "pending" and m["p1_id"] and m["p2_id"]]
            if not ready:
                break
            m = ready[0]
            self.engine.advance_winner(m["id"], m["p1_id"])
            steps += 1
            self.assertLess(steps, 100000, "прогон сетки не сходится")
        ms = self._matches()
        for m in ms:
            self.assertIn(m["status"], ("done", "bye"),
                          f"матч {m['id']} остался {m['status']}")
        by_id = {m["id"]: m for m in ms}
        champions = {m["winner_id"] for m in ms
                     if m["win_next_id"] is None and m["winner_id"] is not None}
        if len(champions) == 0:
            # Переигровка помечена 'bye' без победителя — чемпион тот,
            # кто выиграл Гранд-финал и отправил туда игрока.
            for m in ms:
                nxt = m["win_next_id"]
                if nxt is not None and by_id[nxt]["status"] == "bye" \
                        and by_id[nxt]["winner_id"] is None \
                        and m["winner_id"] is not None:
                    champions.add(m["winner_id"])
        self.assertEqual(len(champions), 1,
                         "чемпион не единственный или не найден")
        champion = next(iter(champions))
        self.assertIn(champion, self.pids,
                      "чемпион не является участником")
        return steps, champion


class TestDoubleEliminationScale(BracketFixture):
    """Double elimination: инварианты для малых и больших сеток."""

    engine_cls = app.DoubleEliminationEngine
    participants = 256

    def test_invariants_small_sizes(self):
        for n in (2, 3, 5, 8, 12):
            ms = self._generate(n)
            self._check_bracket(ms, n)

    def test_invariants_big_sizes(self):
        for n in (32, 64, 128):
            ms = self._generate(n)
            self._check_bracket(ms, n)

    def test_play_through_64(self):
        ms = self._generate(64)
        steps, champion = self._play_through()
        self.assertGreater(steps, 60)

    def test_play_through_128(self):
        ms = self._generate(128)
        steps, champion = self._play_through()
        self.assertGreater(steps, 120)

    def test_generation_time_256(self):
        t0 = time.time()
        ms = self._generate(256)
        self._check_bracket(ms, 256)
        self.assertLess(time.time() - t0, 60,
                        "генерация сетки на 256 участников слишком долгая")

    def test_regenerate_clears_old_and_keeps_generation(self):
        ms1 = self._generate(64)
        ids1 = {m["id"] for m in ms1}
        self.assertEqual(self.db.get_bracket_generation(self.cat, HAND), 0)
        self.db.bump_bracket_generation(self.cat, HAND)
        self.assertEqual(self.db.get_bracket_generation(self.cat, HAND), 1)
        ms2 = self._generate(64)
        ids2 = {m["id"] for m in ms2}
        self.assertFalse(ids1 & ids2, "перегенерация оставила старые матчи")
        self.assertEqual(len(ids2), len(ids1))
        self._check_bracket(ms2, 64)


class TestSingleEliminationScale(BracketFixture):
    """Single elimination: та же проверка."""

    engine_cls = app.SingleEliminationEngine
    bracket_system = "single"
    participants = 512

    def test_invariants_sizes(self):
        for n in (2, 3, 7, 16, 64):
            ms = self._generate(n)
            self._check_bracket(ms, n)

    def test_play_through_256(self):
        ms = self._generate(256)
        steps, champion = self._play_through()
        self.assertGreater(steps, 100)

    def test_generation_time_512(self):
        t0 = time.time()
        ms = self._generate(512)
        self._check_bracket(ms, 512)
        self.assertLess(time.time() - t0, 60)

    def test_odd_sizes_full_play(self):
        for n in (3, 5, 9, 17):
            self._generate(n)
            steps, champion = self._play_through()
            self.assertEqual(steps, n - 1)


class TestMultiCategoryIsolation(unittest.TestCase):
    """Несколько категорий одновременно: сетки не пересекаются."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="armw_multi_cat_")
        app.sync_manager = _SyncStub()
        app.DB_PATH = os.path.join(self.tmp, "multi.db")
        app.PHOTOS_DIR = os.path.join(self.tmp, "photos")
        os.makedirs(app.PHOTOS_DIR, exist_ok=True)
        self.db = app.Database()
        self.tid = self.db.create_tournament("Multi Cat", "21.08.2026", "X")
        self.cats = {}
        for w in range(60, 120, 10):
            cat = self.db.add_category(self.tid, f"{w} кг", w, HAND)
            pids = [self.db.add_participant(self.tid, f"Боец {w}-{i}",
                                            75 + i % 5, "Club", cat, HAND)
                    for i in range(32)]
            self.cats[cat] = pids

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_categories_independent(self):
        engines = {cat: app.DoubleEliminationEngine(self.db)
                   for cat in self.cats}
        for cat, engine in engines.items():
            engine.generate_bracket(self.tid, cat, HAND, self.cats[cat])
        ms = [dict(m) for m in self.db.conn.execute(
            "SELECT * FROM matches WHERE tournament_id=?", (self.tid,))]
        for cat, pids in self.cats.items():
            cat_ms = [m for m in ms if m["category_id"] == cat]
            self.assertEqual(len(cat_ms), 63)  # double elim, 32 участника
            for m in cat_ms:
                for col in ("win_next_id", "lose_next_id"):
                    if m[col] is not None:
                        target = next(x for x in ms if x["id"] == m[col])
                        self.assertEqual(target["category_id"], cat)
        # Играем одну категорию — остальные не меняются.
        cat0, engine0 = next(iter(engines.items()))
        before = {m["id"]: m for m in ms if m["category_id"] != cat0}
        steps = 0
        while True:
            ready = [m for m in ms if m["category_id"] == cat0
                     and m["status"] == "pending"
                     and m["p1_id"] and m["p2_id"]]
            if not ready:
                break
            engine0.advance_winner(ready[0]["id"], ready[0]["p1_id"])
            steps += 1
            self.assertLess(steps, 1000)
            ms = [dict(m) for m in self.db.conn.execute(
                "SELECT * FROM matches WHERE tournament_id=?", (self.tid,))]
        after = {m["id"]: m for m in ms if m["category_id"] != cat0}
        self.assertEqual(before, after)


class TestBracketRoundtrip(BracketFixture):
    """Сетка + сыгранные матчи переносятся между компьютерами целиком."""

    engine_cls = app.DoubleEliminationEngine
    participants = 64

    def test_bracket_survives_export_import(self):
        ms = self._generate(64)
        for _ in range(2):
            ready = [m for m in self._matches()
                     if m["status"] == "pending"
                     and m["p1_id"] and m["p2_id"]]
            self.engine.advance_winner(ready[0]["id"], ready[0]["p1_id"])

        dest = os.path.join(self.tmp, "bracket.armwrestling")
        export_competition(self.db.conn, None, self.tid, dest)

        laptop = Laptop2()
        try:
            import_competition(laptop.db.conn, None, dest,
                               photos_dir=app.PHOTOS_DIR)
            src = [dict(m) for m in self.db.get_matches(self.cat, HAND)]
            dst = [dict(m) for m in laptop.db.get_matches(self.cat, HAND)]
            self.assertEqual(len(src), len(dst))
            for a, b in zip(src, dst):
                self.assertEqual(a, b, f"матч {a['id']} не совпадает "
                                       "после переноса")
            self.assertEqual(
                self.db.get_bracket_generation(self.cat, HAND),
                laptop.db.get_bracket_generation(self.cat, HAND))
            # Прогон продолжается на «втором ноутбуке» до чемпиона.
            engine2 = self.engine_cls(laptop.db)
            steps = 0
            while True:
                ready = [m for m in laptop.db.get_matches(self.cat, HAND)
                         if m["status"] == "pending"
                         and m["p1_id"] and m["p2_id"]]
                if not ready:
                    break
                m = ready[0]
                engine2.advance_winner(m["id"], m["p1_id"])
                steps += 1
                self.assertLess(steps, 100000)
            unfinished = [m for m in laptop.db.get_matches(self.cat, HAND)
                          if m["status"] not in ("done", "bye")]
            self.assertEqual(unfinished, [])
        finally:
            shutil.rmtree(laptop.tmp, ignore_errors=True)

    def test_bracket_import_into_fresh_laptop_same_as_source(self):
        """Чистая проверка: экспорт ещё не начатой сетки и импорт на
        второй ноутбук — структура одинакова."""
        ms = self._generate(64)
        dest = os.path.join(self.tmp, "fresh.armwrestling")
        export_competition(self.db.conn, None, self.tid, dest)
        laptop = Laptop2()
        try:
            import_competition(laptop.db.conn, None, dest,
                               photos_dir=app.PHOTOS_DIR)
            dst = [dict(m) for m in laptop.db.get_matches(self.cat, HAND)]
            self._check_bracket(dst, 64)
        finally:
            shutil.rmtree(laptop.tmp, ignore_errors=True)

    def test_odd_n_bracket_with_byes_roundtrip(self):
        """Нечётное число участников: bye-матчи ('bye' со победителем) и
        ghost-матчи ('done' без победителя) должны переноситься.
        Регрессия: валидаторы экспорта/импорта отвергали статусы
        'waiting'/'bye' и ghost-матчи, порождаемые движком сетки."""
        self._generate(5)
        dest = os.path.join(self.tmp, "odd.armwrestling")
        export_competition(self.db.conn, None, self.tid, dest)
        laptop = Laptop2()
        try:
            import_competition(laptop.db.conn, None, dest,
                               photos_dir=app.PHOTOS_DIR)
            src = [dict(m) for m in self.db.get_matches(self.cat, HAND)]
            dst = [dict(m) for m in laptop.db.get_matches(self.cat, HAND)]
            self.assertEqual(len(src), len(dst))
            for a, b in zip(src, dst):
                self.assertEqual(a, b, f"матч {a['id']} не совпадает "
                                       "после переноса (odd n)")
        finally:
            shutil.rmtree(laptop.tmp, ignore_errors=True)

    def test_collapsed_ghost_matches_pass_integrity(self):
        """Ghost-матчи после _collapse_chained_byes имеют статус 'done' и
        is_bye=0 без участников и победителя. Валидатор экспорта должен
        считать их легитимными (пустые ячейки LB) и не блокировать экспорт.
        Регрессия: пустые ячейки 80/131 в реальном турнире блокировали
        экспорт до того, как валидатор начал опираться на отсутствие
        участников, а не на флаг is_bye."""
        self._generate(10)
        # Эмулируем collapse-матч: пустой, done, без is_bye.
        ghosts = [m for m in self._matches()
                  if (m["p1_id"] is None and m["p2_id"] is None
                      and m["status"] in ("done", "bye"))]
        self.assertTrue(ghosts, "сетка на 10 обязана дать пустые ячейки")
        ms = self.db.get_matches(self.cat, HAND)
        for m in ms:
            if (m["p1_id"] is None and m["p2_id"] is None
                    and m["status"] in ("done", "bye")):
                self.db.conn.execute(
                    "UPDATE matches SET is_bye=0 WHERE id=?", (m["id"],))
        self.db.conn.commit()
        problems = validate_competition_integrity(self.db.conn, self.tid)
        self.assertEqual(problems, [],
                         "ghost-матчи done/is_bye=0 не должны "
                         f"блокировать экспорт: {problems}")
        dest = os.path.join(self.tmp, "ghost.armwrestling")
        export_competition(self.db.conn, None, self.tid, dest)