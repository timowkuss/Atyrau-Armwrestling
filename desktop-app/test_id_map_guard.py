"""Десктопные тесты защиты id_map от многие-к-одному.

Запуск:  python test_id_map_guard.py  (или unittest в папке desktop-app)

Проблема: раньше map_set делал INSERT OR REPLACE по primary key
(entity_type, local_id) и НИЧЕМ не мешал нескольким локальным карточкам
указывать на один remote_id. Так, после потери id_map (переустановка,
второй компьютер) десктоп повторно создавал на сервере тех же спортсменов,
а потом молча привязывал к одному remote несколько локальных карточек —
обратная синхронизация (pull) доставала обновления только до первой из
них, остальные рассинхронизировались, и «виновная» карточка могла оказаться
скрытой.

Теперь: для сущностей с жёстким 1:1 (athlete/coach/club/...) map_set
отказывается привязывать remote_id, уже занятый другой локальной карточкой
(возвращает False, ничего не пишет). athlete_of_participant — исключение:
там многие-к-одному легальны (один спортсмен участвует в нескольких
турнирах).
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sync.state import SyncState  # noqa: E402


class TempStateDb:
    """Временный sync_state.db в изолированной папке."""

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "sync_state.db"

    def cleanup(self):
        self._tmp.cleanup()


class IdMapGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempStateDb()
        self.state = SyncState(self.tmp.path)

    def tearDown(self):
        self.state.close()
        self.tmp.cleanup()

    def test_map_set_ok_first_time(self):
        self.assertTrue(self.state.map_set("athlete", 1, 100))
        self.assertEqual(self.state.map_get("athlete", 1), 100)
        self.assertEqual(self.state.map_get_local("athlete", 100), 1)

    def test_map_set_rejects_many_to_one_for_athlete(self):
        self.assertTrue(self.state.map_set("athlete", 1, 100))
        # вторая локальная карточка на тот же remote — раньше молча писалась
        ok = self.state.map_set("athlete", 2, 100)
        self.assertFalse(ok)
        self.assertEqual(self.state.map_get("athlete", 2), None)
        # первая привязка не тронута
        self.assertEqual(self.state.map_get("athlete", 1), 100)

    def test_map_set_allows_rebind_same_local(self):
        # «перепривязка» той же локальной карточки на другой remote — ок
        self.assertTrue(self.state.map_set("athlete", 1, 100))
        self.assertTrue(self.state.map_set("athlete", 1, 200))
        self.assertEqual(self.state.map_get("athlete", 1), 200)

    def test_map_set_rejects_for_coach_club_etc(self):
        for entity, remote in (("coach", 500), ("club", 600)):
            self.assertTrue(self.state.map_set(entity, 1, remote))
            self.assertFalse(self.state.map_set(entity, 2, remote),
                             f"{entity}: многие-к-одному должно отклоняться")

    def test_athlete_of_participant_many_to_one_allowed(self):
        # легальный случай: один спортсмен на сервере участвует в нескольких
        # турнирах — здесь многие-к-одному НЕ блокируем
        self.assertTrue(self.state.map_set("athlete_of_participant", 1, 900))
        self.assertTrue(self.state.map_set("athlete_of_participant", 2, 900))
        self.assertEqual(self.state.map_get_local("athlete_of_participant", 900), 1)

    def test_different_entity_types_share_remote_id(self):
        # спортсмен и тренер на сервере имеют отдельные счётчики id — их
        # пересечение не конфликт
        self.assertTrue(self.state.map_set("athlete", 1, 100))
        self.assertTrue(self.state.map_set("coach", 1, 100))
        self.assertEqual(self.state.map_get("athlete", 1), 100)
        self.assertEqual(self.state.map_get("coach", 1), 100)

    def test_integrity_check_flags_existing_many_to_one(self):
        # прямой SQL, имитация старого повреждённого состояния
        self.state.map_set("athlete", 1, 100)
        self.state.conn.execute(
            "INSERT INTO id_map (entity_type, local_id, remote_id) "
            "VALUES ('athlete', 2, 100)")
        self.state.conn.commit()
        # проверка из _create_tables отрабатывает без исключений (только логирует)
        self.state._check_id_map_integrity()
        # и защита от новых многие-к-одному не даёт ухудшить дальше
        self.assertFalse(self.state.map_set("athlete", 3, 100))


if __name__ == "__main__":
    unittest.main(verbosity=2)
