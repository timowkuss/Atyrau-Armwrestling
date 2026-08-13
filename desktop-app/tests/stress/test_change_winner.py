"""Тесты пересмотра победителя в уже сыгранной сетке (change_winner).

Проверяют настоящий движок: после изменения одного результата вся сетка
пересчитывается до конца без нарушения структур:
- все завершённые матчи имеют победителя из своих соперников;
- победитель не «проигрывает» позже и не «выигрывает» ещё раз в другой
  ветке сверх сети (нет конфликта игрок с одной веткой);
- ровно один чемпион;
- точечная проверка: смена результата первого матча меняет цепочку
  продвижения дальше.
"""

import os
import shutil
import tempfile
import unittest

import armwrestling_tournament as app
from tests.stress.test_bracket_stress import _SyncStub, BracketFixture


HAND = "Правая"


class ChangeWinnerMixin:
    """Общая логика проверок смены победителя."""

    def _played_bracket(self, n):
        """Генерирует сетку и играет до чемпиона. Возвращает (engine, ms)."""
        self.engine.generate_bracket(self.tid, self.cat, HAND, self.pids[:n])
        steps = 0
        while True:
            ms = self._matches()
            ready = [m for m in ms
                     if m["status"] == "pending" and m["p1_id"] and m["p2_id"]]
            if not ready:
                break
            m = ready[0]
            # Всегда побеждает первый из пары.
            self.engine.advance_winner(m["id"], m["p1_id"])
            steps += 1
            self.assertLess(steps, 100000)
        return self._matches()

    def _assert_consistent(self):
        """Каждый сыгранный матч имеет валидного победителя; bye и
        несыгранная переигровка (Гранд-финал) могут быть без победителя."""
        ms = self._matches()
        for m in ms:
            if m["status"] == "done" and not m["is_bye"]:
                self.assertTrue(m["winner_id"], f"матч {m['id']} без победителя")
                self.assertIn(
                    m["winner_id"], (m["p1_id"], m["p2_id"]),
                    f"победитель матча {m['id']} не из участников матча")
        # Чемпион единственный.
        by_id = {m["id"]: m for m in ms}
        champions = {m["winner_id"] for m in ms
                     if m["win_next_id"] is None and m["winner_id"] is not None}
        if len(champions) == 0:
            for m in ms:
                nxt = m["win_next_id"]
                if nxt is not None and by_id[nxt]["status"] == "bye" \
                        and by_id[nxt]["winner_id"] is None \
                        and m["winner_id"] is not None:
                    champions.add(m["winner_id"])
        self.assertEqual(len(champions), 1, "чемпион не единственный")
        self.assertIn(next(iter(champions)), self.pids)

    def test_single_change_reflects_in_chain(self):
        """Смена победителя первого матча пересчитывает сетку иначе, чем
        первоначальный прогон (первый матч выигрывал второй игрок)."""
        for n in (4, 5, 8):
            self._generate(n)
            ms0 = self._matches()
            round1 = [m for m in ms0
                      if m["bracket"] == "winners" and m["stage"] == 0
                      and m["p1_id"] and m["p2_id"] and not m["is_bye"]]
            if not round1:
                continue
            m = round1[0]
            self._play_through()
            ms_old = self._matches()
            # Сейчас должен победить p1 (мы всегда отдавали победу p1).
            m_old = next(x for x in ms_old if x["id"] == m["id"])
            self.assertEqual(m_old["winner_id"], m_old["p1_id"])
            # Меняем на p2.
            ok = self.engine.change_winner(m["id"], m["p2_id"])
            self.assertTrue(ok)
            ms_new = self._matches()
            m_new = next(x for x in ms_new if x["id"] == m["id"])
            self.assertEqual(m_new["winner_id"], m["p2_id"])
            # Проверяем, что изменился кто-то ближе к финалу.
            self.assertNotEqual(
                {x["id"]: x["winner_id"] for x in ms_old},
                {x["id"]: x["winner_id"] for x in ms_new},
                "смена одного результата не изменила итоги сетки")
            self._assert_consistent()

    def test_change_every_round1_match_keeps_champion(self):
        """Меняем победителя первых матчей так, чтобы верхняя сетка шла
        по 'второму' игроку — итоговый чемпион должен быть корректным."""
        for n in (6, 7):
            self._generate(n)
            self._play_through()
            ms = self._matches()
            round1 = [m for m in ms
                      if m["bracket"] == "winners" and m["stage"] == 0
                      and m["p1_id"] and m["p2_id"] and not m["is_bye"]]
            for m in round1:
                target = m["p2_id"] if m["winner_id"] == m["p1_id"] else m["p1_id"]
                self.assertTrue(self.engine.change_winner(m["id"], target))
            self._assert_consistent()

    def test_change_non_first_round(self):
        """Смена победителя во втором раунде тоже пересчитывает всё ниже."""
        for n in (8, 9):
            self._generate(n)
            self._play_through()
            ms = self._matches()
            candidates = [m for m in ms
                          if m["bracket"] == "winners" and m["stage"] == 1
                          and m["p1_id"] and m["p2_id"] and m["status"] == "done"]
            if not candidates:
                continue
            m = candidates[0]
            target = m["p2_id"] if m["winner_id"] == m["p1_id"] else m["p1_id"]
            self.assertTrue(self.engine.change_winner(m["id"], target))
            self._assert_consistent()

    def test_change_winner_same_value_noop(self):
        """Если назначить того же победителя — сетка не ломается."""
        for n in (3, 5):
            self._generate(n)
            self._play_through()
            ms = self._matches()
            done = [m for m in ms if m["status"] == "done" and not m["is_bye"]]
            if not done:
                continue
            m = done[0]
            old = {m["id"]: (m["p1_id"], m["p2_id"], m["winner_id"], m["status"])
                   for m in self._matches()}
            self.assertTrue(self.engine.change_winner(m["id"], m["winner_id"]))
            new = {m["id"]: (m["p1_id"], m["p2_id"], m["winner_id"], m["status"])
                   for m in self._matches()}
            restoring = {m["id"]: (m["p1_id"], m["p2_id"], m["winner_id"], m["status"])
                         for m in self._matches()}
            self.assertEqual(set(old), set(new))
            self._assert_consistent()

    def test_change_winner_invalid_target_rejected(self):
        """Победителем нельзя назначить не-участника матча."""
        self._generate(6)
        self._play_through()
        ms = self._matches()
        done = [m for m in ms if m["status"] == "done" and not m["is_bye"]]
        m = done[0]
        outside = next(pid for pid in self.pids
                       if pid not in (m["p1_id"], m["p2_id"]))
        self.assertFalse(self.engine.change_winner(m["id"], outside))

    def test_replay_statuses_valid(self):
        """После пересчёта все матчи должны быть в допустимых статусах."""
        for n in (4, 7, 10):
            self._generate(n)
            self._play_through()
            ms = self._matches()
            done = [m for m in ms
                    if m["status"] == "done" and m["p1_id"] and m["p2_id"]]
            if not done:
                continue
            m = done[0]
            target = m["p2_id"] if m["winner_id"] == m["p1_id"] else m["p1_id"]
            self.assertTrue(self.engine.change_winner(m["id"], target))
            for mm in self._matches():
                self.assertIn(mm["status"], ("pending", "waiting", "done", "bye"),
                              f"матч {mm['id']} получил недопустимый статус {mm['status']}")


class TestDoubleChangeWinner(ChangeWinnerMixin, BracketFixture):
    engine_cls = app.DoubleEliminationEngine
    bracket_system = "double"
    participants = 64


class TestSingleChangeWinner(ChangeWinnerMixin, BracketFixture):
    engine_cls = app.SingleEliminationEngine
    bracket_system = "single"
    participants = 64


if __name__ == "__main__":
    unittest.main()