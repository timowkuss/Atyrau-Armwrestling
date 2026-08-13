"""Регрессия: create_match, чей mid уже замаплен на сервер, не должен
повторно уходить в сеть и блокировать FIFO-очередь.

Сценарий из продакшена: в офлайн-очереди осталась строка create_match для
mid=1 (старый турнир), а сам матч давно создан на сервере (id_map уже
содержит remote_id). Раньше _replay слал повторный POST → сервер отвечал
422 («участники не принадлежат категории», состав категории с тех пор
изменился) → flush_pending возвращался сразу и ВСЯ очередь позади (в т.ч.
реальные create_match текущего турнира) застревала навсегда.
"""

import os
import tempfile
import unittest

from sync.sync_manager import SyncManager
from sync.state import SyncState


class _ReplayApi:
    """Фейковый API: create_match считает ВСЕ вызовы сетевыми и возвращает
    ошибку — если _replay повторно позвонит в сеть, тест упадёт."""

    def __init__(self):
        self.create_match_calls = []

    def create_match(self, **kwargs):
        self.create_match_calls.append(kwargs)
        raise RuntimeError("create_match повторно вызван в сеть — это баг")

    def flush_pending(self):
        pass


class TestCreateMatchAlreadyMapped(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="armw_replay_")
        self.api = _ReplayApi()
        self.state = SyncState(os.path.join(self.tmp, "sync_state.db"))
        self.mgr = SyncManager(api_client=self.api, state=self.state)
        self.mgr.enabled = True

    def test_create_match_already_mapped_does_not_block_queue(self):
        """mid=1 уже замаплен (remote 175) → create_match из очереди
        снимается без выхода в сеть, и операция ПОЗАДИ него доезжает."""
        self.state.map_set("category", 1, 10)   # категория существует на сервере
        self.state.map_set("match", 1, 175)     # матч уже создан

        # Заблокированная строка create_match для уже-созданного матча...
        self.state.enqueue("create_match", {
            "mid": 1, "category_id": 1, "tournament_id": 1, "hand": "Правая",
            "round_name": "1/2 финала WB", "bracket": "winners", "match_order": 0,
            "stage": 0, "p1_id": None, "p2_id": None, "winner_id": None,
            "p1_losses": 0, "p2_losses": 0, "is_bye": 0, "status": "pending",
        })
        # ...и ПОЗАДИ него — строка, которую реально надо создать.
        self.state.enqueue("create_match", {
            "mid": 2, "category_id": 1, "tournament_id": 1, "hand": "Правая",
            "round_name": "1/4 финала WB", "bracket": "winners", "match_order": 1,
            "stage": 0, "p1_id": None, "p2_id": None, "winner_id": None,
            "p1_losses": 0, "p2_losses": 0, "is_bye": 0, "status": "pending",
        })
        # Вторая строка тоже пусть будет уже создана (иначе _replay пойдёт
        # в сеть через self.api.create_match и упадёт по задумке теста).
        self.state.map_set("match", 2, 176)

        succeeded, remaining = self.mgr.flush_pending()

        self.assertEqual(remaining, 0,
                         "очередь не должна застрять на уже-созданном матче")
        self.assertEqual(self.api.create_match_calls, [],
                         "_replay не должен звонить в сеть для замапленных mid")
        self.assertEqual(succeeded, 2,
                         "обе строки должны быть сняты как выполненные")

    def test_create_match_without_map_still_goes_to_network(self):
        """Контрольный тест: НЕзамапленный mid по-прежнему уходит в сеть
        (т.е. новый ранний return не прячет реальные create_match)."""
        self.state.map_set("category", 1, 10)
        self.state.enqueue("create_match", {
            "mid": 99, "category_id": 1, "tournament_id": 1, "hand": "Правая",
            "round_name": "1/4 финала WB", "bracket": "winners", "match_order": 0,
            "stage": 0, "p1_id": None, "p2_id": None, "winner_id": None,
            "p1_losses": 0, "p2_losses": 0, "is_bye": 0, "status": "pending",
        })

        self.mgr.flush_pending()

        self.assertEqual(len(self.api.create_match_calls), 1,
                         "незамапленный create_match обязан дойти до сети")


if __name__ == "__main__":
    unittest.main()
