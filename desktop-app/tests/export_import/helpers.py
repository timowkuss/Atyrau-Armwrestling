"""Общие хелперы тестов экспорта/импорта соревнования.

Тесты строят реальный сценарий «ноутбук №1» через настоящий Database из
armwrestling_tournament (та же логика, что и в приложении), затем
экспортируют в .armwrestling и импортируют во «второй ноутбук» (свежая
папка с новой БД и новым SyncState).

sync_manager подменяется заглушкой: сеть в тестах недоступна, поэтому
все _synced_*-обёртки должны просто выполнять локальную запись.
"""

import os
import sys
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import armwrestling_tournament as app  # noqa: E402
from club_rating import finalize_competition  # noqa: E402
from sync.state import SyncState  # noqa: E402


class _NoSync:
    """Заглушка синхронизации: сеть не нужна, операции просто записываются
    локально (dispatch_* вызывается воркерами в фоне и игнорируется)."""

    state = None

    def dispatch_async(self, f):
        pass

    def dispatch_match_update_async(self, *a, **k):
        pass

    def on_match_created(self, *a, **k):
        pass

    def enqueue(self, *a, **k):
        pass


class Scenario:
    """Полный сценарий: соревнование, категории, участники, спортсмены,
    клубы, тренеры, матчи (завершённый + незавершённый), начисленный
    клубный рейтинг, pending-очередь и id_map."""

    def __init__(self, finished=True):
        self.tmp = tempfile.mkdtemp(prefix="armw_export_import_")
        app.sync_manager = _NoSync()
        app.DB_PATH = os.path.join(self.tmp, "src.db")
        app.PHOTOS_DIR = os.path.join(self.tmp, "photos")
        os.makedirs(app.PHOTOS_DIR, exist_ok=True)
        self.db = app.Database()
        self.state = SyncState(os.path.join(self.tmp, "src_sync.db"))

        self.tid = self.db.create_tournament("Test Cup 2026", "10.08.2026",
                                             "Testville")
        self.club_a = self.db.add_club("Bears", "City A")
        self.club_b = self.db.add_club("Wolves", "City B")
        self.coach = self.db.add_coach("Coach One", club="Bears",
                                       club_id=self.club_a)
        self.ath_a = self.db.add_athlete("Ivan", "Petrov", "1990-01-01", "M",
                                         club="Bears", coach_id=self.coach,
                                         club_id=self.club_a)
        self.ath_b = self.db.add_athlete("Petr", "Sidorov", "1992-02-02", "M",
                                         club="Wolves", club_id=self.club_b)

        self.cat = self.db.add_category(self.tid, "80 кг", 80, "Правая")
        self.p1 = self.db.add_participant(self.tid, "Иванов Иван", 79.5,
                                          "Bears", self.cat, "Правая",
                                          athlete_id=self.ath_a)
        self.p2 = self.db.add_participant(self.tid, "Петров Пётр", 80.2,
                                          "Wolves", self.cat, "Правая",
                                          athlete_id=self.ath_b)

        self.m_done = self.db.save_match({
            "tournament_id": self.tid, "category_id": self.cat,
            "hand": "Правая", "round_name": "Финал", "bracket": "winners",
            "match_order": 1, "p1_id": self.p1, "p2_id": self.p2,
            "status": "done", "winner_id": self.p1,
            "p1_losses": 0, "p2_losses": 0, "is_bye": 0})
        self.m_pending = self.db.save_match({
            "tournament_id": self.tid, "category_id": self.cat,
            "hand": "Правая", "round_name": "1/2", "bracket": "winners",
            "match_order": 2, "p1_id": self.p2, "p2_id": None,
            "status": "pending", "winner_id": None,
            "p1_losses": 0, "p2_losses": 0, "is_bye": 0})

        # Рейтинг: завершаем турнир и начисляем очки (идемпотентно).
        if finished:
            self.db.finish_tournament(self.tid)
            finalize_competition(self.db.conn, self.tid)

        # Очередь sync: операция соревнования (должна переехать) + чужая
        # операция другого соревнования (переезжать не должна).
        self.state.enqueue("update_match", {
            "tid": self.tid, "mid": self.m_done,
            "category_id": self.cat, "pid": self.p2, "winner_id": self.p1})
        self.state.enqueue("create_tournament", {
            "tid": 999, "name": "Other", "date": "01.01.2026"})
        _pending = self.state.pending()
        self.op_tid = _pending[-2]["id"]
        self.op_foreign = _pending[-1]["id"]
        self.state.map_set("competition", self.tid, 9001)
        self.state.map_set("category", self.cat, 8001)
        self.state.map_set("participant", self.p1, 7001)
        self.state.map_set("participant", self.p2, 7002)
        self.state.map_set("match", self.m_done, 6001)
        self.state.map_set("match", self.m_pending, 6002)
        self.state.map_set("athlete", self.ath_a, 5001)
        self.state.map_set("athlete", self.ath_b, 5002)
        self.state.map_set("coach", self.coach, 4001)
        self.state.map_set("club", self.club_a, 3001)
        self.state.map_set("club", self.club_b, 3002)
        self.state.map_set("athlete_of_participant", self.p1, self.ath_a)

    def export(self, dest, password=None, include_photos=False, emergency=False):
        from transfer.exporter import export_competition
        return export_competition(self.db.conn, self.state, self.tid, dest,
                                  password=password,
                                  include_photos=include_photos,
                                  emergency=emergency)


class Laptop2:
    """«Ноутбук №2»: полностью свежая папка с собственной БД и sync_state."""

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="armw_laptop2_")
        app.DB_PATH = os.path.join(self.tmp, "dst.db")
        app.PHOTOS_DIR = os.path.join(self.tmp, "photos")
        os.makedirs(app.PHOTOS_DIR, exist_ok=True)
        self.db = app.Database()
        self.state = SyncState(os.path.join(self.tmp, "dst_sync.db"))

    def import_file(self, src, password=None, force_replace=False):
        from transfer.importer import import_competition
        return import_competition(self.db.conn, self.state, src,
                                  password=password,
                                  force_replace=force_replace,
                                  photos_dir=app.PHOTOS_DIR)


def snapshot(db, tid):
    """Плоский снапшот всех таблиц соревнования для сравнения."""
    return {
        "tournament": dict(db.conn.execute(
            "SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()),
        "categories": [dict(r) for r in db.conn.execute(
            "SELECT * FROM weight_categories WHERE tournament_id=?", (tid,))],
        "participants": [dict(r) for r in db.conn.execute(
            "SELECT * FROM participants WHERE tournament_id=?", (tid,))],
        "matches": [dict(r) for r in db.conn.execute(
            "SELECT * FROM matches WHERE tournament_id=?", (tid,))],
        "athletes": [dict(r) for r in db.conn.execute(
            "SELECT a.* FROM athletes a JOIN participants p "
            "ON p.athlete_id=a.id WHERE p.tournament_id=?", (tid,))],
        "clubs": [dict(r) for r in db.conn.execute(
            "SELECT c.* FROM clubs c JOIN athletes a ON a.club_id=c.id "
            "JOIN participants p ON p.athlete_id=a.id WHERE p.tournament_id=?",
            (tid,))],
        "history": [dict(r) for r in db.conn.execute(
            "SELECT * FROM club_rating_history WHERE tournament_id=?",
            (tid,))],
    }


def assert_snapshot_equal(testcase, src_snap, dst_snap, tid):
    testcase.assertEqual(src_snap["categories"], dst_snap["categories"])
    testcase.assertEqual(src_snap["participants"], dst_snap["participants"])
    testcase.assertEqual(src_snap["matches"], dst_snap["matches"])
    testcase.assertEqual(src_snap["athletes"], dst_snap["athletes"])
    testcase.assertEqual(src_snap["clubs"], dst_snap["clubs"])
    testcase.assertEqual(src_snap["history"], dst_snap["history"])
    t1 = dict(src_snap["tournament"])
    t2 = dict(dst_snap["tournament"])
    t1.pop("session_id", None)
    t2.pop("session_id", None)
    testcase.assertEqual(t1, t2)
