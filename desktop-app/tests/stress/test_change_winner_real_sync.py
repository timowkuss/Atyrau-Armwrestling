"""Полный путь синка с НАСТОЯЩИМ SyncManager (воркер-поток, SyncState,
офлайн-очередь, _replay). Проверяет жалобу «сменил победителя A vs B → B,
а на сайте в следующем матче всё ещё A vs C»: нижестоящий матч обязан
получить нового участника (B), а не только статус/winner_id изменённого
матча.

Два режима:
  live   — сеть живая, on_match_updated шлёт PATCH сразу;
  offline — force_queue=True: апдейты падают в офлайн-очередь и уходят
  через flush_pending()/replay. Именно offline-путь когда-то НЕ слал
  p1_id/p2_id нижестоящего матча (см. sync_manager._replay) — статус и
  победитель долетали, а новая пара в следующем раунде не появлялась.
"""

import os
import tempfile
import unittest

import armwrestling_tournament as app
from sync.sync_manager import SyncManager
from sync.state import SyncState
from sync.api_client import ApiClientError
from tests.stress.test_bracket_stress import BracketFixture

HAND = "Правая"


class _FakeApi:
    """Эмулятор backend: хранит remote_matches и применяет PATCH'и."""

    def __init__(self):
        self.remote_matches = {}
        self.patches = []

    def update_match(self, remote_match_id, **kwargs):
        self.patches.append((remote_match_id, dict(kwargs)))
        if remote_match_id in self.remote_matches:
            self.remote_matches[remote_match_id].update(kwargs)

    def flush_pending(self):
        pass


class TestChangeWinnerRealSync(BracketFixture):
    engine_cls = app.DoubleEliminationEngine
    bracket_system = "double"
    participants = 32
    has_ghost_collapse = True  # схлопывание пустых слотов в done — только double

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="armw_real_sync_")
        self.api = _FakeApi()
        self.state = SyncState(os.path.join(self.tmp, "sync_state.db"))
        self.mgr = SyncManager(api_client=self.api, state=self.state)
        self.mgr.enabled = True
        app.sync_manager = self.mgr

        app.DB_PATH = os.path.join(self.tmp, "bracket.db")
        app.PHOTOS_DIR = os.path.join(self.tmp, "photos")
        os.makedirs(app.PHOTOS_DIR, exist_ok=True)
        self.db = app.Database()
        self.tid = self.db.create_tournament(
            "RS 2026", "20.08.2026", "City", bracket_system="double")
        self.cat = self.db.add_category(self.tid, "80 кг", 80, HAND)
        self.pids = []
        for i in range(self.participants):
            self.pids.append(self.db.add_participant(
                self.tid, f"Боец {i}", 75 + i % 5, "Club", self.cat, HAND))
        self.engine = self.engine_cls(self.db)

    def tearDown(self):
        app.sync_manager = None

    def _map_all(self):
        for mid in [m["id"] for m in self._matches()]:
            self.state.map_set("match", mid, mid * 100 + 1)
        for pid in self.pids:
            self.state.map_set("participant", pid, pid * 10 + 2)

    def _seed_server(self):
        ms = self._matches()
        to_remote_pid = lambda pid: self.state.map_get("participant", pid) if pid else None
        for m in ms:
            rid = self.state.map_get("match", m["id"])
            self.api.remote_matches[rid] = {
                "winner_id": to_remote_pid(m["winner_id"]),
                "status": m["status"],
                "p1_id": to_remote_pid(m["p1_id"]),
                "p2_id": to_remote_pid(m["p2_id"]),
            }

    def _play(self, win_p1=True):
        while True:
            ms = self._matches()
            ready = [m for m in ms
                     if m["status"] == "pending" and m["p1_id"] and m["p2_id"]]
            if not ready:
                break
            m = ready[0]
            self.engine.advance_winner(m["id"], m["p1_id"] if win_p1 else m["p2_id"])

    def _drain(self):
        self.mgr._sync_queue.join()

    def _purge_pending(self):
        self.state.conn.execute("DELETE FROM pending_queue")
        self.state.conn.commit()

    def _fresh_change(self, offline):
        self._generate(8)
        self._play(win_p1=True)
        self._map_all()
        self._seed_server()
        # create_* из генерации сетки фейковый API не принял (нет методов) —
        # вычищаем их, чтобы в офлайн-очереди остались ТОЛЬКО свежие
        # update_match от change_winner (иначе они блокируют flush_pending).
        # Сначала дожидаемся, пока воркер доенакгирует все create_* из
        # _generate/_play — иначе они попадут в очередь ПОСЛЕ нашего purge.
        self._drain()
        self._purge_pending()
        self.mgr.force_queue = offline

        ms = self._matches()
        target = next(m for m in ms if m["status"] == "done" and not m["is_bye"])
        other = target["p2_id"] if target["winner_id"] == target["p1_id"] else target["p1_id"]
        self.api.patches.clear()

        ok = self.engine.change_winner(target["id"], other)
        self.assertTrue(ok)

        # Воркер может ещё не успеть сложить все update_match в офлайн-очередь —
        # ждём его строго до любых проверок/флаша, чтобы не было гонки.
        self._drain()

        if offline:
            self.assertTrue(self.state.pending_count() > 0,
                            "при force_queue апдейты обязаны уйти в офлайн-очередь")
            self.mgr.flush_pending()

        return target, other

    _run_live = _fresh_change.__get__(object)

    def _assert_server_converged(self, target, other):
        remote_pid = lambda pid: self.state.map_get("participant", pid) if pid else None
        local = {m["id"]: m for m in self._matches()}
        for mid, m in local.items():
            rid = self.state.map_get("match", mid)
            server = self.api.remote_matches.get(rid)
            self.assertIsNotNone(server, f"матч {mid}: нет remote")
            self.assertEqual(server.get("winner_id"), remote_pid(m["winner_id"]),
                             f"матч {mid}: server winner != local")
            self.assertEqual(server.get("status"), m["status"],
                             f"матч {mid}: server status != local")
            self.assertEqual(server.get("p1_id"), remote_pid(m["p1_id"]),
                             f"матч {mid}: server p1 != local")
            self.assertEqual(server.get("p2_id"), remote_pid(m["p2_id"]),
                             f"матч {mid}: server p2 != local")

    # ── live: PATCH летит сразу ────────────────────────────────────────
    def test_live_path_downstream_participant_reaches_server(self):
        target, other = self._fresh_change(offline=False)
        self.assertTrue(self.api.patches, "live-путь не отправил ни одного PATCH")
        self._assert_server_converged(target, other)

    def test_live_path_changed_round1_downstream(self):
        # Берём матч первого раунда: у него ВСЕГДА есть нижестоящий матч,
        # чьи участники должны измениться на сайте.
        self._generate(8)
        self._play(win_p1=True)
        self._map_all()
        self._seed_server()

        ms = self._matches()
        round0 = [m for m in ms if m["status"] == "done"
                  and m["stage"] == 0 and m["bracket"] == "winners"]
        target = round0[0]
        other = target["p2_id"] if target["winner_id"] == target["p1_id"] else target["p1_id"]
        self.assertTrue(other)

        old_p1 = target["p1_id"]
        old_advance = list(target.values())
        # Кто ушёл в следующий матч при старом исходе (A) и должен смениться на B.
        next_m = None
        for m in self._matches():
            if m["p1_id"] == old_p1 or m["p2_id"] == old_p1:
                if m["status"] != "done" or m["id"] != target["id"]:
                    next_m = m
                    break
        self.assertIsNotNone(next_m, "не нашли нижестоящий матч для старого победителя")

        self.api.patches.clear()
        self.mgr.force_queue = False

        ok = self.engine.change_winner(target["id"], other)
        self.assertTrue(ok)
        self._drain()

        # Нижестоящий матч на сервере теперь содержит НОВОГО победителя (B).
        rid = self.state.map_get("match", next_m["id"])
        server = self.api.remote_matches[rid]
        remote_old = self.state.map_get("participant", old_p1)
        self.assertNotEqual(server.get("p1_id"), remote_old)
        self.assertNotEqual(server.get("p2_id"), remote_old)

    # ── offline: апдейты уходят через офлайн-очередь и replay ──────────
    def test_offline_queue_downstream_participant_reaches_server(self):
        target, other = self._fresh_change(offline=True)
        self.assertTrue(self.api.patches,
                        "offline-путь (flush_pending) не отправил ни одного PATCH")
        self._assert_server_converged(target, other)

    def test_offline_queue_no_leftovers(self):
        _, _ = self._fresh_change(offline=True)
        self.assertEqual(self.state.pending_count(), 0,
                         "после flush_pending в очереди не должно оставаться апдейтов")

    def test_ghost_matches_reach_server_after_change(self):
        """Структурные ghost-матчи (пустые слоты, схлопнутые в done при
        пересчёте) обязаны долететь до сервера. Раньше _resolve_all_byes
        обновлял их сырым SQL без _sync_match — на сайте такие матчи навсегда
        оставались waiting («пустые пары в сетке/очереди»), хотя в десктопе
        были done. Нечётное число участников гарантирует наличие ghosts."""
        if not getattr(self, "has_ghost_collapse", False):
            self.skipTest("схлопывание ghost-слотов — только double elimination")
        self._generate(10)
        self._play(win_p1=True)
        self._map_all()
        self._seed_server()
        self._purge_pending()
        self.mgr.force_queue = False

        ghosts_before = [m for m in self._matches()
                         if m["status"] == "done" and not m["p1_id"] and not m["p2_id"]]
        self.assertTrue(ghosts_before, "сетка из 10 обязана дать ghost-матчи")

        ms = self._matches()
        target = next(m for m in ms if m["status"] == "done" and not m["is_bye"])
        other = target["p2_id"] if target["winner_id"] == target["p1_id"] else target["p1_id"]
        self.api.patches.clear()

        ok = self.engine.change_winner(target["id"], other)
        self.assertTrue(ok)
        self._drain()

        for gm in ghosts_before:
            rid = self.state.map_get("match", gm["id"])
            server = self.api.remote_matches.get(rid)
            self.assertIsNotNone(server, f"ghost матч {gm['id']} не создан на сервере")
            self.assertEqual(server.get("status"), "done",
                             f"ghost матч {gm['id']} на сервере не стал done")

    def test_ghost_matches_offline_flush(self):
        """Те же ghost-матчи, но через офлайн-очередь + flush_pending."""
        if not getattr(self, "has_ghost_collapse", False):
            self.skipTest("схлопывание ghost-слотов — только double elimination")
        self._generate(10)
        self._play(win_p1=True)
        self._map_all()
        self._seed_server()
        self._purge_pending()
        self.mgr.force_queue = True

        ghosts_before = [m for m in self._matches()
                         if m["status"] == "done" and not m["p1_id"] and not m["p2_id"]]
        self.assertTrue(ghosts_before)

        ms = self._matches()
        target = next(m for m in ms if m["status"] == "done" and not m["is_bye"])
        other = target["p2_id"] if target["winner_id"] == target["p1_id"] else target["p1_id"]
        self.api.patches.clear()

        self.assertTrue(self.engine.change_winner(target["id"], other))
        self._drain()  # дать воркеру сложить все update_match в офлайн-очередь
        self.mgr.flush_pending()
        self.assertEqual(self.state.pending_count(), 0,
                         "после flush_pending в очереди не должно оставаться апдейтов")

        for gm in ghosts_before:
            rid = self.state.map_get("match", gm["id"])
            server = self.api.remote_matches.get(rid)
            self.assertIsNotNone(server, f"ghost матч {gm['id']} не создан на сервере")
            self.assertEqual(server.get("status"), "done",
                             f"ghost матч {gm['id']} на сервере не стал done")


class TestSingleChangeWinnerRealSync(TestChangeWinnerRealSync):
    engine_cls = app.SingleEliminationEngine
    bracket_system = "single"
    participants = 32
    has_ghost_collapse = False


if __name__ == "__main__":
    unittest.main()