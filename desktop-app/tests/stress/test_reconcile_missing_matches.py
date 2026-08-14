"""Reconcile: матчи, существующие локально, но отсутствующие на сайте
(нет записи в id_map), ставятся в очередь create_match — сетка
самовосстанавливается, когда сервер потерял матчи.

Сценарий из продакшена: правая рука «Senior Men 100kg Both» была
полностью разыграна локально (mid 60-84), но на сайте отсутствовала
вообще — create_match для неё никогда не был создан, а приложение при
запуске не сверяло локальную БД с id_map. Reconcile закрывает этот пробел.
"""

import os
import sqlite3
import tempfile
import unittest

from sync.sync_manager import SyncManager
from sync.state import SyncState


def make_local_db(path, competition_id=2, category_id=3):
    """Минимальная локальная БД турнира с несколькими сыгранными матчами."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE tournaments (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE categories (id INTEGER PRIMARY KEY, tournament_id INTEGER)")
    conn.execute(
        "CREATE TABLE matches ("
        " id INTEGER PRIMARY KEY, tournament_id INTEGER, category_id INTEGER, "
        " hand TEXT, round_name TEXT, bracket TEXT, match_order INTEGER, "
        " p1_id INTEGER, p2_id INTEGER, winner_id INTEGER, "
        " p1_losses INTEGER, p2_losses INTEGER, is_bye INTEGER, "
        " status TEXT, stage INTEGER, table_number INTEGER)"
    )
    conn.execute("INSERT INTO tournaments (id) VALUES (?)", (competition_id,))
    conn.execute("INSERT INTO categories (id, tournament_id) VALUES (?,?)",
                 (category_id, competition_id))
    for mid in (60, 61, 62):
        conn.execute(
            "INSERT INTO matches (id, tournament_id, category_id, hand, round_name, "
            "bracket, match_order, p1_id, p2_id, winner_id, p1_losses, p2_losses, "
            "is_bye, status, stage, table_number) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (mid, competition_id, category_id, "Правая", "1/8 финала WB", "winners",
             0, 31, 24, 31, 0, 0, 0, "done", 0, 1),
        )
    conn.commit()
    conn.close()


class _SilentApi:
    """Никаких сетевых вызовов в тесте reconcile — всё должно остаться в очереди."""

    def create_match(self, **kwargs):
        raise AssertionError("reconcile обязан добавлять в очередь, а не слать в сеть")

    def update_match(self, **kwargs):
        raise AssertionError("не ожидаем сетевых вызовов")

    def flush_pending(self):
        pass


class TestReconcileMissingMatches(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="armw_reconcile_")
        self.local_db = os.path.join(self.tmp, "armwrestling.db")
        self.state_db = os.path.join(self.tmp, "sync_state.db")
        make_local_db(self.local_db)
        self.api = _SilentApi()
        self.state = SyncState(self.state_db)
        self.mgr = SyncManager(api_client=self.api, state=self.state)
        self.mgr.enabled = True

    def test_unmapped_matches_get_create_match_in_queue(self):
        """Матчи без записи в id_map попадают в очередь create_match."""
        self.state.map_set("category", 3, 8)      # категория уже на сервере
        self.state.map_set("participant", 31, 32) # участники уже замаплены
        self.state.map_set("participant", 24, 25)

        added = self.mgr.reconcile_missing_matches(2, db_path=self.local_db)

        self.assertEqual(added, 3, "все три матча должны быть восстановлены")
        self.assertEqual(self.state.pending_count(), 3)
        self.assertEqual(self.state.pending()[0]["operation"], "create_match")

    def test_already_mapped_match_not_requeued(self):
        """Матч, который уже синхронизирован (id_map есть), не дублируется."""
        self.state.map_set("category", 3, 8)
        self.state.map_set("match", 61, 296)      # уже на сайте
        self.state.map_set("participant", 31, 32)
        self.state.map_set("participant", 24, 25)

        added = self.mgr.reconcile_missing_matches(2, db_path=self.local_db)

        self.assertEqual(added, 2, "mapped mid=61 не должен пересоздаваться")
        queue_mids = []
        for row in self.state.pending():
            import json
            queue_mids.append(json.loads(row["payload"])["mid"])
        self.assertNotIn(61, queue_mids)
        self.assertEqual(sorted(queue_mids), [60, 62])

    def test_unmapped_category_skipped(self):
        """Без маппинга категории матчи не создаются (иначе create_match
        навсегда повиснет в очереди как «ждёт category_id»)."""
        added = self.mgr.reconcile_missing_matches(2, db_path=self.local_db)

        self.assertEqual(added, 0, "категория не замаплена — нечего восстанавливать")
        self.assertEqual(self.state.pending_count(), 0)

    def test_unmapped_participants_skipped(self):
        """Матч, чьи участники не замаплены, пропускается с предупреждением
        (сервер бы ответил 422 и операция застряла бы в blocked)."""
        self.state.map_set("category", 3, 8)      # категория есть,
        # но участники (31, 24) — не замаплены

        added = self.mgr.reconcile_missing_matches(2, db_path=self.local_db)

        self.assertEqual(added, 0, "участники не замаплены — матч не создаём")
        self.assertEqual(self.state.pending_count(), 0)

    def test_other_tournament_not_touched(self):
        """Матчи ДРУГОГО турнира не восстанавливаются (чтобы не воскрешать
        сирот удалённых соревнований)."""
        self.state.map_set("category", 3, 8)
        self.state.map_set("participant", 31, 32)
        self.state.map_set("participant", 24, 25)

        added = self.mgr.reconcile_missing_matches(999, db_path=self.local_db)

        self.assertEqual(added, 0, "другой турнир не должен затрагиваться")


if __name__ == "__main__":
    unittest.main()