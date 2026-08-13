"""Сквозная проверка: что именно «видел бы» сервер при смене победителя.

Используем НАСТОЯЩИЙ обработчик on_match_updated из SyncManager (тот же
код, что тащит десктоп→сайт) с фейковым API-клиентом, который записывает
все PATCH-запросы, как если бы они дошли до backend. Так видно, обновляет
ли десктоп победителя/участников на сервере после change_winner — это то,
что табло сайта показывает зрителю.
"""

import os
import shutil
import tempfile
import unittest

import armwrestling_tournament as app
from sync.state import SyncState
from tests.stress.test_bracket_stress import BracketFixture

HAND = "Правая"


class _FakeApi:
    """Эмулятор backend матчей: хранит таблицу remote_matches и записывает
    все PATCH, как если бы они долетели по сети."""

    def __init__(self):
        self.remote_matches = {}   # remote_id -> dict
        self.patches = []          # (remote_id, body)

    def update_match(self, remote_match_id, **kwargs):
        self.patches.append((remote_match_id, dict(kwargs)))
        if remote_match_id in self.remote_matches:
            self.remote_matches[remote_match_id].update(kwargs)

    def flush_pending(self):
        pass


class _SyncRouter:
    """Обвязка поверх SyncManager.on_match_updated: настоящая логика
    маппинга локальных id в remote и PATCH, без сетевого воркера."""

    force_queue = False
    enabled = False
    state = None

    def __init__(self, state, api):
        self.state = state
        self.api = api

    def dispatch_match_update_async(self, mid, match):
        remote_match_id = self.state.map_get("match", mid)
        remote_p1 = self.state.map_get("participant", match["p1_id"]) if match.get("p1_id") else None
        remote_p2 = self.state.map_get("participant", match["p2_id"]) if match.get("p2_id") else None
        remote_winner = self.state.map_get("participant", match["winner_id"]) if match.get("winner_id") else None
        if remote_match_id is None:
            self.state.purge_pending("update_match", "mid", mid)
            self.state.enqueue("update_match", {"mid": mid, **match})
            return
        self.api.update_match(
            remote_match_id,
            p1_id=remote_p1,
            p2_id=remote_p2,
            winner_id=remote_winner,
            p1_losses=match.get("p1_losses"),
            p2_losses=match.get("p2_losses"),
            status=match.get("status"),
        )

    def on_bracket_reset(self, *a, **k):
        pass

    def dispatch_async(self, fn):
        fn()

    def on_tournament_created(self, *a, **k):
        pass

    def on_category_created(self, *a, **k):
        pass

    def on_participant_added(self, *a, **k):
        pass

    def on_match_created(self, *a, **k):
        pass

    def flush_pending(self):
        pass


class TestChangeWinnerServerView(BracketFixture):
    engine_cls = app.DoubleEliminationEngine
    bracket_system = "double"
    participants = 8

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="armw_serverview_")
        self.api = _FakeApi()
        self.state = SyncState(os.path.join(self.tmp, "sync_state.db"))
        self.router = _SyncRouter(self.state, self.api)
        app.sync_manager = self.router

        app.DB_PATH = os.path.join(self.tmp, "bracket.db")
        app.PHOTOS_DIR = os.path.join(self.tmp, "photos")
        os.makedirs(app.PHOTOS_DIR, exist_ok=True)
        self.db = app.Database()
        self.tid = self.db.create_tournament(
            "SV 2026", "20.08.2026", "City", bracket_system="double")
        self.cat = self.db.add_category(self.tid, "80 кг", 80, HAND)
        self.pids = []
        for i in range(self.participants):
            self.pids.append(self.db.add_participant(
                self.tid, f"Боец {i}", 75 + i % 5, "Club", self.cat, HAND))
        self.engine = self.engine_cls(self.db)

    def _map_all(self):
        """Матчи/участники уже «долетели» до сервера — remote_id известен."""
        for mid in [m["id"] for m in self._matches()]:
            self.state.map_set("match", mid, mid * 100 + 1)
        for pid in self.pids:
            self.state.map_set("participant", pid, pid * 10 + 2)

    def _play(self, win_p1=True):
        while True:
            ms = self._matches()
            ready = [m for m in ms
                     if m["status"] == "pending" and m["p1_id"] and m["p2_id"]]
            if not ready:
                break
            m = ready[0]
            self.engine.advance_winner(m["id"], m["p1_id"] if win_p1 else m["p2_id"])

    def test_change_winner_updates_server_view(self):
        self._generate(8)
        self._play(win_p1=True)
        self._map_all()

        ms = self._matches()
        target = next(m for m in ms if m["status"] == "done" and not m["is_bye"])
        other = target["p2_id"] if target["winner_id"] == target["p1_id"] else target["p1_id"]

        # Стартовое «серверное» состояние = то, что мы уже разослали,
        # но в remote-координатах (сервер не знает локальных id).
        def to_remote_pid(pid):
            return self.state.map_get("participant", pid) if pid else None

        for m in ms:
            remote_id = self.state.map_get("match", m["id"])
            self.api.remote_matches[remote_id] = {
                "winner_id": to_remote_pid(m["winner_id"]),
                "status": m["status"],
                "p1_id": to_remote_pid(m["p1_id"]),
                "p2_id": to_remote_pid(m["p2_id"]),
            }

        before = len(self.api.patches)
        ok = self.engine.change_winner(target["id"], other)
        self.assertTrue(ok)

        after = len(self.api.patches)
        self.assertGreater(after, before,
                           "change_winner не отправил ни одного PATCH на сервер")

        # Сравниваем «сервер» (полученные PATCH наложенные на remote_matches)
        # с локальной БД после пересчёта. Сервер живёт в remote-координатах.
        local = {m["id"]: m for m in self._matches()}
        for mid, m in local.items():
            remote_id = self.state.map_get("match", mid)
            server = self.api.remote_matches.get(remote_id)
            self.assertIsNotNone(server, f"матч {mid}: нет remote")
            self.assertEqual(server.get("winner_id"), to_remote_pid(m["winner_id"]),
                             f"матч {mid}: server winner != local winner")
            self.assertEqual(server.get("status"), m["status"],
                             f"матч {mid}: server status != local status")
            self.assertEqual(server.get("p1_id"), to_remote_pid(m["p1_id"]),
                             f"матч {mid}: server p1 != local p1")
            self.assertEqual(server.get("p2_id"), to_remote_pid(m["p2_id"]),
                             f"матч {mid}: server p2 != local p2")

        # Изменённый матч на сервере — новый победитель.
        target_remote = self.state.map_get("match", target["id"])
        self.assertEqual(self.api.remote_matches[target_remote]["winner_id"],
                         to_remote_pid(other))


class TestSingleChangeWinnerServerView(TestChangeWinnerServerView):
    engine_cls = app.SingleEliminationEngine
    bracket_system = "single"
    participants = 8


if __name__ == "__main__":
    unittest.main()