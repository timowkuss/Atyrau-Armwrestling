"""Тесты занятости столов трансляции (broadcast table occupancy).

Раньше проверка «свободный ли стол» смотрела только на ОТКРЫТЫЕ окна сеток.
Но номер стола сохраняется в БД и переживает закрытие окна: если категория A
уже транслирует стол 1, а её окно закрыто, категория B при включении
трансляции не должна снова получать стол 1. Тесты проверяют, что занятые
номера учитываются и по открытым окнам, и по БД.
"""

import os
import shutil
import tempfile
import types
import unittest

import armwrestling_tournament as app


HAND = "Правая"


def _fake_win(db, cat_id, cat_name, table_number=None, master=None, tournament_id=None):
    """Лёгкая заглушка окна сетки с нужными для методов атрибутами."""
    w = types.SimpleNamespace()
    w.db = db
    w.tournament_id = tournament_id
    w.category = {"id": cat_id, "name": cat_name}
    w.hand = HAND
    w.table_number = table_number
    w.master = master or types.SimpleNamespace(_open_bracket_windows=[])
    w.winfo_exists = lambda: True
    # Привязываем реальные методы движка из класса BracketWindow.
    w._suggest_table_number = types.MethodType(
        app.BracketWindow._suggest_table_number, w)
    w._find_broadcast_conflict = types.MethodType(
        app.BracketWindow._find_broadcast_conflict, w)
    return w


class TableOccupancyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="armw_table_")
        app.DB_PATH = os.path.join(self.tmp, "tables.db")
        app.PHOTOS_DIR = os.path.join(self.tmp, "photos")
        os.makedirs(app.PHOTOS_DIR, exist_ok=True)
        self.db = app.Database()
        self.tid = self.db.create_tournament("T", "20.08.2026", "X")
        self.cat_a = self.db.add_category(self.tid, "A кг", 80, HAND)
        self.cat_b = self.db.add_category(self.tid, "B кг", 85, HAND)
        for c in (self.cat_a, self.cat_b):
            for i in range(4):
                self.db.add_participant(self.tid, f"P{c}-{i}", 75, "Club", c, HAND)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _seed_matches(self, cat):
        eng = app.DoubleEliminationEngine(self.db)
        pids = [p["id"] for p in self.db.get_participants_by_category(cat)]
        eng.generate_bracket(self.tid, cat, HAND, pids)

    def test_suggests_2_when_table_1_persisted_other_bracket(self):
        """Категория A транслирует стол 1 (сохранено в БД, окно закрыто) —
        категории B должен предлагаться стол 2."""
        self._seed_matches(self.cat_a)
        self._seed_matches(self.cat_b)
        self.db.set_bracket_table_number(self.cat_a, HAND, 1)

        b = _fake_win(self.db, self.cat_b, "B кг", table_number=None, tournament_id=self.tid)
        self.assertEqual(b._suggest_table_number(), 2)

    def test_suggests_1_when_all_others_free(self):
        """Никто не занят — первый свободный стол 1."""
        self._seed_matches(self.cat_a)
        self._seed_matches(self.cat_b)
        a = _fake_win(self.db, self.cat_a, "A кг", table_number=None, tournament_id=self.tid)
        self.assertEqual(a._suggest_table_number(), 1)

    def test_suggests_3_when_1_and_2_taken(self):
        """Столы 1 и 2 заняты другими категориями — предлагается 3."""
        self._seed_matches(self.cat_a)
        self._seed_matches(self.cat_b)
        self.db.set_bracket_table_number(self.cat_a, HAND, 1)
        # Вторая «другая» категория — имитируем ещё одно сохранённое окно.
        cat_c = self.db.add_category(self.tid, "C кг", 90, HAND)
        for i in range(4):
            self.db.add_participant(self.tid, f"PC-{i}", 76, "Club", cat_c, HAND)
        self._seed_matches(cat_c)
        self.db.set_bracket_table_number(cat_c, HAND, 2)

        b = _fake_win(self.db, self.cat_b, "B кг", table_number=None, tournament_id=self.tid)
        self.assertEqual(b._suggest_table_number(), 3)

    def test_conflict_detected_from_db_after_window_closed(self):
        """Окно категории A закрыто, но стол 1 сохранён — конфликт всё равно
        виден (предупреждение «другая категория с сохранённой трансляцией»)."""
        self._seed_matches(self.cat_a)
        self._seed_matches(self.cat_b)
        self.db.set_bracket_table_number(self.cat_a, HAND, 1)

        b = _fake_win(self.db, self.cat_b, "B кг", table_number=None, tournament_id=self.tid)
        self.assertIsNotNone(b._find_broadcast_conflict(1))

    def test_no_conflict_for_own_bracket(self):
        """Собственная категория на своём столе — не конфликт."""
        self._seed_matches(self.cat_a)
        self._seed_matches(self.cat_b)
        self.db.set_bracket_table_number(self.cat_a, HAND, 1)

        a = _fake_win(self.db, self.cat_a, "A кг", table_number=1, tournament_id=self.tid)
        self.assertIsNone(a._find_broadcast_conflict(1))

    def test_open_windows_still_count(self):
        """Открытое окно другой категории со столом 1 учитывается и без БД."""
        self._seed_matches(self.cat_a)
        self._seed_matches(self.cat_b)
        master = types.SimpleNamespace(_open_bracket_windows=[])
        a = _fake_win(self.db, self.cat_a, "A кг", table_number=1, master=master, tournament_id=self.tid)
        master._open_bracket_windows.append(a)
        b = _fake_win(self.db, self.cat_b, "B кг", table_number=None, master=master, tournament_id=self.tid)
        master._open_bracket_windows.append(b)

        self.assertEqual(b._suggest_table_number(), 2)
        self.assertEqual(b._find_broadcast_conflict(1), "A кг — Правая")


if __name__ == "__main__":
    unittest.main()

