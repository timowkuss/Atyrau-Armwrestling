"""Отладочный тест: что именно улетает на сервер при смене победителя.

change_winner → _replay_bracket_results пересобирает сетку. Важно понять,
долетит ли до сервера новый победитель изменённого матча и обновлённые
участники последующих матчей (табло сайта показывает очередь по столам
из pending/waiting матчей, так что без этих апдейтов изменение на табло
не видно).
"""

import os
import shutil
import tempfile
import unittest

import armwrestling_tournament as app
from tests.stress.test_bracket_stress import BracketFixture

HAND = "Правая"


class _RecordingSync:
    """Заглушка sync_manager, которая запоминает все dispatch-вызовы и
    payload-ы match-апдейтов в порядке вызова."""

    force_queue = False
    enabled = False

    def __init__(self):
        self.calls = []  # (mid, payload_snapshot)

    def dispatch_match_update_async(self, mid, match):
        self.calls.append((mid, dict(match)))

    def dispatch_async(self, fn):
        pass

    def on_bracket_reset(self, category_id, hand, local_mids):
        pass

    def on_match_created(self, *a, **k):
        pass

    def flush_pending(self):
        pass

    def enqueue(self, *a, **k):
        pass


class TestChangeWinnerSync(BracketFixture):
    engine_cls = app.DoubleEliminationEngine
    bracket_system = "double"
    participants = 8

    def setUp(self):
        super().setUp()
        self.rec = _RecordingSync()
        app.sync_manager = self.rec

    def _play(self, win_p1=True):
        while True:
            ms = self._matches()
            ready = [m for m in ms
                     if m["status"] == "pending" and m["p1_id"] and m["p2_id"]]
            if not ready:
                break
            m = ready[0]
            self.engine.advance_winner(m["id"], m["p1_id"] if win_p1 else m["p2_id"])

    def test_changed_matches_are_redispatched(self):
        """НИ ОДИН матч, чьё состояние изменилось в результате смены
        победителя, не должен «замолчать»: для него обязан уйти финальный
        апдейт. Раньше часть матчей пересчитывалась локально, но не
        рассылалась заново, и табло сайта показывало старую пару/старого
        победителя."""
        self._generate(8)
        self._play(win_p1=True)

        before = {m["id"]: dict(m) for m in self._matches()}
        ms = self._matches()
        target = next(m for m in ms if m["status"] == "done" and not m["is_bye"])
        other = target["p2_id"] if target["winner_id"] == target["p1_id"] else target["p1_id"]

        self.rec.calls.clear()
        ok = self.engine.change_winner(target["id"], other)
        self.assertTrue(ok)

        after = {m["id"]: dict(m) for m in self._matches()}

        def state(s):
            return (s["p1_id"], s["p2_id"], s["winner_id"], s["status"])

        changed_ids = {mid for mid in after if state(after[mid]) != state(before.get(mid, {}))}

        last_by_mid = {}
        for mid, payload in self.rec.calls:
            last_by_mid[mid] = payload

        for mid in changed_ids:
            self.assertIn(mid, last_by_mid,
                          f"матч {mid} изменился, но не был разослан повторно")
            p = last_by_mid[mid]
            self.assertEqual(state(p), state(after[mid]),
                             f"матч {mid}: разосланное финальное состояние не совпадает")

    def test_change_winner_dispatches_sync(self):
        self._generate(8)
        self._play(win_p1=True)
        ms = self._matches()
        done = [m for m in ms if m["status"] == "done" and not m["is_bye"]]
        target = done[0]
        other = target["p2_id"] if target["winner_id"] == target["p1_id"] else target["p1_id"]

        ok = self.engine.change_winner(target["id"], other)
        self.assertTrue(ok)

        # После смены победителя сетка заново разослана (актуальные апдейты
        # улетели), и последний апдейт каждого матча — его финальное
        # состояние: оно должно совпадать с локальной БД (иначе табло
        # на сайте покажет другое).
        dispatched = set(mid for mid, _ in self.rec.calls)
        self.assertEqual(dispatched, set(m["id"] for m in self._matches()),
                         "не все матчи сетки были разосланы после пересчёта")

        changed_payloads = [p for mid, p in self.rec.calls if mid == target["id"]]
        self.assertTrue(changed_payloads)
        last = changed_payloads[-1]
        self.assertEqual(last["winner_id"], other)

        for m in self._matches():
            payloads = [p for mid, p in self.rec.calls if mid == m["id"]]
            if not payloads:
                continue
            final = payloads[-1]
            self.assertEqual(final["winner_id"], m["winner_id"],
                             f"матч {m['id']}: рассинхрон winner")
            self.assertEqual(final["status"], m["status"],
                             f"матч {m['id']}: рассинхрон status")
            self.assertEqual(final["p1_id"], m["p1_id"],
                             f"матч {m['id']}: рассинхрон p1")
            self.assertEqual(final["p2_id"], m["p2_id"],
                             f"матч {m['id']}: рассинхрон p2")


class TestSingleChangeWinnerSync(TestChangeWinnerSync):
    engine_cls = app.SingleEliminationEngine
    bracket_system = "single"
    participants = 8


if __name__ == "__main__":
    unittest.main()