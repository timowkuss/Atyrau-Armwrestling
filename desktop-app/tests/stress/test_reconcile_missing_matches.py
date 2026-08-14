"""Reconcile: матчи, существующие локально, но отсутствующие на сайте
(нет записи в id_map), ставятся в очередь create_match — сетка
самовосстанавливается, когда сервер потерял матчи.

Сценарий из продакшена: правая рука «Senior Men 100kg Both» была
полностью разыграна локально (mid 60-84), но на сайте отсутствовала
вообще — create_match для неё никогда не был создан, а приложение при
запуске не сверяло локальную БД с id_map. Reconcile закрывает этот пробел.

Покрытие edge-случаев:
  * дубли create_match при повторном вызове reconcile (нет сети) — НЕ плодим;
  * повторный reconcile после успешного создания (id_map проставлен) — не
    добавляет лишний create_match;
  * bye-матчи (p2=None) восстанавливаются;
  * pending-матчи без winner (winner_id=None) восстанавливаются;
  * частичный маппинг участников (p1 есть, p2 нет) — матч пропускается;
  * отсутствующая/битая локальная БД — return 0 без исключений.
"""

import json
import os
import sqlite3
import tempfile
import unittest

from sync.sync_manager import SyncManager
from sync.state import SyncState


def make_local_db(path, tournament_id=2, category_id=3, matches=None,
                  with_matches_table=True):
    """Минимальная локальная БД турнира. matches — список кортежей вида
    (id, hand, round_name, p1_id, p2_id, winner_id, is_bye, status)."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE tournaments (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE categories (id INTEGER PRIMARY KEY, tournament_id INTEGER)")
    if with_matches_table:
        conn.execute(
            "CREATE TABLE matches ("
            " id INTEGER PRIMARY KEY, tournament_id INTEGER, category_id INTEGER, "
            " hand TEXT, round_name TEXT, bracket TEXT, match_order INTEGER, "
            " p1_id INTEGER, p2_id INTEGER, winner_id INTEGER, "
            " p1_losses INTEGER, p2_losses INTEGER, is_bye INTEGER, "
            " status TEXT, stage INTEGER, table_number INTEGER)"
        )
    conn.execute("INSERT INTO tournaments (id) VALUES (?)", (tournament_id,))
    conn.execute("INSERT INTO categories (id, tournament_id) VALUES (?,?)",
                 (category_id, tournament_id))
    if matches:
        for i, m in enumerate(matches):
            mid, hand, round_name, p1, p2, winner, is_bye, status = m
            conn.execute(
                "INSERT INTO matches (id, tournament_id, category_id, hand, round_name, "
                "bracket, match_order, p1_id, p2_id, winner_id, p1_losses, p2_losses, "
                "is_bye, status, stage, table_number) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (mid, tournament_id, category_id, hand, round_name, "winners",
                 i, p1, p2, winner, 0, 0, is_bye, status, 0, None),
            )
    conn.commit()
    conn.close()


# базовые три матча правой руки Senior (все done, p1/p2/winner замаплены)
_BASIC = [
    (60, "Правая", "1/8 финала WB", 31, 24, 31, 0, "done"),
    (61, "Правая", "1/8 финала WB", 29, 28, 29, 0, "done"),
    (62, "Правая", "1/8 финала WB", 30, 27, 27, 0, "done"),
]


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
        self.state_db = os.path.join(self.tmp, "sync_state.db")
        self.api = _SilentApi()
        self.state = SyncState(self.state_db)
        self.mgr = SyncManager(api_client=self.api, state=self.state)
        self.mgr.enabled = True
        # стандартный маппинг: категория и участники 60-62 на сервере
        self.state.map_set("category", 3, 8)
        self.state.map_set("participant", 31, 32)
        self.state.map_set("participant", 24, 25)
        self.state.map_set("participant", 29, 30)
        self.state.map_set("participant", 28, 29)
        self.state.map_set("participant", 30, 31)
        self.state.map_set("participant", 27, 28)

    def _local_db(self, tournament_id=2, category_id=3, matches=None, **kw):
        path = os.path.join(self.tmp, "armwrestling.db")
        make_local_db(path, tournament_id=tournament_id, category_id=category_id,
                      matches=matches, **kw)
        return path

    def _pending_mids(self):
        mids = []
        for row in self.state.pending():
            mids.append(json.loads(row["payload"])["mid"])
        return sorted(mids)

    # ── базовое поведение ─────────────────────────────────────
    def test_unmapped_matches_get_create_match_in_queue(self):
        db = self._local_db(matches=_BASIC)
        added = self.mgr.reconcile_missing_matches(2, db_path=db)
        self.assertEqual(added, 3)
        self.assertEqual(self.state.pending_count(), 3)
        self.assertEqual(self.state.pending()[0]["operation"], "create_match")
        self.assertEqual(self._pending_mids(), [60, 61, 62])

    def test_already_mapped_match_not_requeued(self):
        self.state.map_set("match", 61, 296)   # уже на сайте
        db = self._local_db(matches=_BASIC)
        added = self.mgr.reconcile_missing_matches(2, db_path=db)
        self.assertEqual(added, 2)
        self.assertEqual(self._pending_mids(), [60, 62])

    def test_repeated_reconcile_no_duplicates(self):
        """Повторный reconcile при недоступной сети (create_match всё ещё в
        очереди, id_map не проставлен) НЕ должен плодить дубли."""
        db = self._local_db(matches=_BASIC)
        first = self.mgr.reconcile_missing_matches(2, db_path=db)
        second = self.mgr.reconcile_missing_matches(2, db_path=db)
        third = self.mgr.reconcile_missing_matches(2, db_path=db)
        self.assertEqual(first, 3)
        self.assertEqual(second, 0, "дубли добавлять нельзя")
        self.assertEqual(third, 0)
        self.assertEqual(self.state.pending_count(), 3)

    def test_reconcile_after_success_no_duplicate(self):
        """После того как create_match долетел (id_map проставлен), повторный
        reconcile ничего не добавляет."""
        db = self._local_db(matches=_BASIC)
        self.mgr.reconcile_missing_matches(2, db_path=db)
        # flush «доставил»: mid 60-62 получили remote id
        for mid, rid in zip((60, 61, 62), (295, 296, 297)):
            self.state.map_set("match", mid, rid)
            self.state.mark_done(self.state.pending()[0]["id"])
        added = self.mgr.reconcile_missing_matches(2, db_path=db)
        self.assertEqual(added, 0)
        self.assertEqual(self.state.pending_count(), 0)

    # ── структура матчей (bye / pending / разные руки) ─────────
    def test_bye_match_without_p2_created(self):
        """bye-матч (p2=None, winner=p1) с замапленным p1 восстанавливается."""
        bye = _BASIC + [(63, "Правая", "1/4 финала WB", 31, None, 31, 1, "bye")]
        self.state.map_set("participant", 31, 32)  # уже есть
        db = self._local_db(matches=bye)
        added = self.mgr.reconcile_missing_matches(2, db_path=db)
        self.assertEqual(added, 4)
        self.assertIn(63, self._pending_mids())

    def test_pending_match_without_winner_created(self):
        """pending-матч с winner_id=None восстанавливается (None — корректно)."""
        pending = [(70, "Правая", "Финал WB", 31, 24, None, 0, "pending")]
        db = self._local_db(matches=pending)
        added = self.mgr.reconcile_missing_matches(2, db_path=db)
        self.assertEqual(added, 1)
        self.assertEqual(self._pending_mids(), [70])

    def test_both_hands_reconciled(self):
        """Матчи обеих рук одной категории восстанавливаются."""
        both = _BASIC + [(100, "Левая", "1/8 финала WB", 31, 24, 31, 0, "done")]
        # для левой руки участники те же
        db = self._local_db(matches=both)
        added = self.mgr.reconcile_missing_matches(2, db_path=db)
        self.assertEqual(added, 4)

    # ── маппинг участников ─────────────────────────────────────
    def test_partial_participant_mapping_skipped(self):
        """p1 замаплен, p2 — нет → только этот матч пропускается (сервер
        дал бы 422), остальные с полным маппингом добавляются."""
        # убираем маппинг участников 24 (p2 матча 60) — для 61/62 маппинг цел
        self.state.map_delete("participant", 24)
        db = self._local_db(matches=_BASIC)
        added = self.mgr.reconcile_missing_matches(2, db_path=db)
        self.assertEqual(added, 2, "матч 60 (незамапленный p2) должен быть пропущен")
        self.assertEqual(self._pending_mids(), [61, 62], "61 и 62 добавляются")

    def test_unmapped_category_skipped(self):
        """Без маппинга категории матчи не создаются."""
        self.state.map_delete("category", 3)
        db = self._local_db(matches=_BASIC)
        added = self.mgr.reconcile_missing_matches(2, db_path=db)
        self.assertEqual(added, 0)

    def test_other_tournament_not_touched(self):
        db = self._local_db(matches=_BASIC)
        added = self.mgr.reconcile_missing_matches(999, db_path=db)
        self.assertEqual(added, 0)

    # ── устойчивость к битым данным ────────────────────────────
    def test_missing_local_db_returns_zero(self):
        missing = os.path.join(self.tmp, "no_such.db")
        added = self.mgr.reconcile_missing_matches(2, db_path=missing)
        self.assertEqual(added, 0)

    def test_broken_local_db_schema_returns_zero(self):
        """БД без таблицы matches (экспортный файл, старая схема) → 0, без
        исключения наружу."""
        db = self._local_db(matches=None, with_matches_table=False)
        added = self.mgr.reconcile_missing_matches(2, db_path=db)
        self.assertEqual(added, 0)

    def test_empty_tournament_returns_zero(self):
        db = self._local_db(matches=[])
        added = self.mgr.reconcile_missing_matches(2, db_path=db)
        self.assertEqual(added, 0)


if __name__ == "__main__":
    unittest.main()