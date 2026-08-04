"""Десктопные тесты скрытия тренеров/спортсменов и офлайн-синка.

Покрывают:
  * каскады при скрытии (Database._original_set_coach_hidden /
    _original_set_athlete_hidden / _original_delete_*): отпускание учеников,
    выход из клуба, штраф -10 рейтингу, «Показать» ничего не восстанавливает;
  * секции «Скрытые» (search_hidden_coaches / count_hidden_coaches) и
    исключение скрытых из обычных списков;
  * офлайн-очередь -> flush_pending: create/update тренера не теряют phone и
    is_hidden; delete тренера/спортсмена доезжают до сервера;
  * pull-синк скрытых карточек: скрытого тренера не заводим локально, у
    существующих чистим привязки (зеркально серверу).
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import armwrestling_tournament as app  # noqa: E402
from club_rating import REASON_ATHLETE_REMOVED, add_points, get_club_rating  # noqa: E402
import sync.sync_manager as sync_manager_module  # noqa: E402
from sync.pull_sync import PullSyncManager  # noqa: E402
from sync.state import SyncState  # noqa: E402
from sync.sync_manager import SyncManager  # noqa: E402


class FakeApi:
    """Запоминает вызовы; даёт сквозные remote-id при create."""

    def __init__(self):
        self.calls = []
        self._next_coach = 1000
        self._next_athlete = 2000

    def create_coach(self, **kw):
        self.calls.append(("create_coach", None, dict(kw)))
        self._next_coach += 1
        return {"id": self._next_coach}

    def update_coach(self, remote_id, **kw):
        self.calls.append(("update_coach", remote_id, dict(kw)))
        return {"status": "ok"}

    def delete_coach(self, remote_id):
        self.calls.append(("delete_coach", remote_id, None))
        return {"status": "ok"}

    def create_athlete(self, **kw):
        self.calls.append(("create_athlete", None, dict(kw)))
        self._next_athlete += 1
        return {"id": self._next_athlete}

    def update_athlete(self, remote_id, **kw):
        self.calls.append(("update_athlete", remote_id, dict(kw)))
        return {"status": "ok"}

    def delete_athlete(self, remote_id):
        self.calls.append(("delete_athlete", remote_id, None))
        return {"status": "ok"}


class TempDb:
    """Временная папка с armwrestling.db (для Database) и sync_state.db."""

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.tournament_path = self.dir / "armwrestling.db"
        self.state_path = self.dir / "sync_state.db"

    def make_database(self) -> "app.Database":
        app.DB_PATH = self.tournament_path
        return app.Database()

    def cleanup(self):
        self._tmp.cleanup()


class HideCascadeDbTest(unittest.TestCase):
    """Каскады скрытия на локальной БД (вызов оригиналов, без сети)."""

    def setUp(self):
        self.tmp = TempDb()
        self.db = self.tmp.make_database()
        self.club_id = self.db.add_club("Алга")
        self.coach_id = self.db.add_coach(
            "Иванов Иван", club="Алга", phone="+77771112233", club_id=self.club_id
        )
        self.athlete_id = self.db.add_athlete(
            "Петров", "Пётр", "01.01.2000", "M", club="Алга",
            coach_id=self.coach_id, club_id=self.club_id,
        )

    def tearDown(self):
        self.db.conn.close()
        self.tmp.cleanup()

    def _athlete(self, aid):
        return self.db.conn.execute(
            "SELECT * FROM athletes WHERE id=?", (aid,)).fetchone()

    def _coach(self, cid):
        return self.db.conn.execute(
            "SELECT * FROM coaches WHERE id=?", (cid,)).fetchone()

    def test_coach_hide_releases_students_and_leaves_club(self):
        app._original_set_coach_hidden(self.db, self.coach_id, True)
        c = self._coach(self.coach_id)
        self.assertEqual(c["is_hidden"], 1)
        self.assertIsNone(c["club_id"])
        self.assertEqual(c["club"], "")
        self.assertIsNone(self._athlete(self.athlete_id)["coach_id"])
        self.assertEqual(self._athlete(self.athlete_id)["club_id"], self.club_id)

    def test_coach_hide_moves_to_hidden_section_only(self):
        app._original_set_coach_hidden(self.db, self.coach_id, True)
        self.assertNotIn(self.coach_id, [c["id"] for c in self.db.get_coaches()])
        self.assertEqual(self.db.count_hidden_coaches(), 1)
        hidden = self.db.search_hidden_coaches()
        self.assertEqual([c["id"] for c in hidden], [self.coach_id])
        self.assertNotIn(
            self.coach_id, [c["id"] for c in self.db.get_coaches("Иванов")])

    def test_coach_show_does_not_restore_anything(self):
        app._original_set_coach_hidden(self.db, self.coach_id, True)
        app._original_set_coach_hidden(self.db, self.coach_id, False)
        c = self._coach(self.coach_id)
        self.assertEqual(c["is_hidden"], 0)
        self.assertIsNone(c["club_id"])
        self.assertIsNone(self._athlete(self.athlete_id)["coach_id"])
        self.assertIn(self.coach_id, [c["id"] for c in self.db.get_coaches()])

    def test_coach_delete_releases_students(self):
        app._original_delete_coach(self.db, self.coach_id)
        self.assertIsNone(self._coach(self.coach_id))
        self.assertIsNone(self._athlete(self.athlete_id)["coach_id"])

    def test_athlete_hide_detaches_and_penalizes_club(self):
        add_points(self.db.conn, self.club_id, self.athlete_id, None, 100,
                   "SEED", "seed")
        self.assertEqual(get_club_rating(self.db.conn, self.club_id), 100)
        app._original_set_athlete_hidden(self.db, self.athlete_id, True)
        a = self._athlete(self.athlete_id)
        self.assertEqual(a["is_hidden"], 1)
        self.assertIsNone(a["club_id"])
        self.assertIsNone(a["coach_id"])
        self.assertEqual(a["club"], "")
        self.assertEqual(a["club_active"], 0)
        self.assertIsNone(a["join_club_date"])
        self.assertEqual(get_club_rating(self.db.conn, self.club_id), 90)
        hist = self.db.conn.execute(
            "SELECT reason FROM club_rating_history WHERE club_id=? AND points=-10",
            (self.club_id,)).fetchall()
        self.assertEqual([h["reason"] for h in hist], [REASON_ATHLETE_REMOVED])

    def test_athlete_delete_penalizes_club(self):
        add_points(self.db.conn, self.club_id, self.athlete_id, None, 100,
                   "SEED", "seed")
        app._original_delete_athlete(self.db, self.athlete_id)
        self.assertIsNone(self._athlete(self.athlete_id))
        self.assertEqual(get_club_rating(self.db.conn, self.club_id), 90)

    def test_get_athletes_by_coach_excludes_hidden(self):
        app._original_set_athlete_hidden(self.db, self.athlete_id, True)
        self.assertEqual(
            [a["id"] for a in self.db.get_athletes_by_coach(self.coach_id)], [])

    def test_hidden_athlete_not_in_regular_search(self):
        app._original_set_athlete_hidden(self.db, self.athlete_id, True)
        self.assertEqual(
            [a["id"] for a in self.db.search_athletes("Петров")], [])
        self.assertEqual(
            [a["id"] for a in self.db.search_hidden_athletes()],
            [self.athlete_id])


class OfflineSyncTest(unittest.TestCase):
    """Офлайн-очередь -> flush_pending: не теряем phone/is_hidden и deletes."""

    def setUp(self):
        self.tmp = TempDb()
        self.db = self.tmp.make_database()
        # Объяснение для _coach_exists_locally: обновления тренеров читают
        # armwrestling.db из модуля sync.sync_manager — указываем на временную.
        sync_manager_module._TOURNAMENT_DB_PATH = self.tmp.tournament_path
        self.api = FakeApi()
        self.mgr = SyncManager(
            api_client=self.api, state=SyncState(self.tmp.state_path))
        self.mgr.force_queue = True
        self._orig_sync_manager = app.sync_manager

    def tearDown(self):
        app.sync_manager = self._orig_sync_manager
        self.mgr.state.close()
        self.db.conn.close()
        self.tmp.cleanup()

    def _flush(self):
        self.mgr.force_queue = False
        succeeded, remaining = self.mgr.flush_pending()
        return succeeded, remaining

    def test_offline_coach_hide_flush_keeps_phone_and_is_hidden(self):
        # create уходит в очередь, update ждёт create — payload сохраняет
        # и phone (попутный баг), и is_hidden (скрытие).
        self.mgr.on_coach_created(
            1, "Иванов Иван", "Алга", None, None, phone="+77771112233")
        self.mgr.on_coach_updated(
            1, "Иванов Иван", "Алга", None, None, phone="+77771112233",
            is_hidden=True)
        self.assertEqual(self.mgr.state.pending_count(), 2)

        succeeded, remaining = self._flush()
        self.assertEqual(remaining, 0)
        self.assertEqual(succeeded, 2)
        create_call = [c for c in self.api.calls if c[0] == "create_coach"]
        self.assertEqual(len(create_call), 1)
        self.assertEqual(create_call[0][2]["phone"], "+77771112233")
        update_call = [c for c in self.api.calls if c[0] == "update_coach"]
        self.assertEqual(len(update_call), 1)
        _, remote_id, kw = update_call[0]
        self.assertIsInstance(remote_id, int)
        self.assertTrue(kw["is_hidden"])
        self.assertEqual(kw["phone"], "+77771112233")

    def test_offline_coach_update_with_remote_id_sends_is_hidden(self):
        # Уже синхронизированный тренер: скрытие офлайн -> очередь -> flush
        # шлёт update_coach с is_hidden=True на правильный remote_id.
        self.mgr.state.map_set("coach", 1, 4242)
        self.mgr.on_coach_updated(
            1, "Иванов Иван", "Алга", None, None, phone="+77771112233",
            is_hidden=True)
        succeeded, remaining = self._flush()
        self.assertEqual(remaining, 0)
        self.assertEqual(succeeded, 1)
        update_call = [c for c in self.api.calls if c[0] == "update_coach"]
        self.assertEqual(len(update_call), 1)
        _, remote_id, kw = update_call[0]
        self.assertEqual(remote_id, 4242)
        self.assertTrue(kw["is_hidden"])
        self.assertEqual(kw["phone"], "+77771112233")

    def test_offline_coach_delete_flush_sends_delete(self):
        self.mgr.state.map_set("coach", 1, 4242)
        self.mgr.on_coach_deleted(1)
        succeeded, remaining = self._flush()
        self.assertEqual(remaining, 0)
        self.assertEqual(succeeded, 1)
        delete_calls = [c for c in self.api.calls if c[0] == "delete_coach"]
        self.assertEqual(len(delete_calls), 1)
        self.assertEqual(delete_calls[0][1], 4242)

    def test_offline_athlete_hide_flush_sends_is_hidden(self):
        self.mgr.state.map_set("athlete", 1, 8080)
        self.mgr.on_athlete_updated(
            1, "Петров", "Пётр", "01.01.2000", "M", "Алга", "", None,
            coach_name="", iin="", phone="+77772223344", is_hidden=True)
        succeeded, remaining = self._flush()
        self.assertEqual(remaining, 0)
        self.assertEqual(succeeded, 1)
        update_calls = [c for c in self.api.calls if c[0] == "update_athlete"]
        self.assertEqual(len(update_calls), 1)
        _, remote_id, kw = update_calls[0]
        self.assertEqual(remote_id, 8080)
        self.assertTrue(kw["is_hidden"])

    def test_offline_athlete_delete_flush_sends_delete(self):
        self.mgr.state.map_set("athlete", 1, 8080)
        self.mgr.on_athlete_deleted(1)
        succeeded, remaining = self._flush()
        self.assertEqual(remaining, 0)
        self.assertEqual(succeeded, 1)
        delete_calls = [c for c in self.api.calls if c[0] == "delete_athlete"]
        self.assertEqual(len(delete_calls), 1)
        self.assertEqual(delete_calls[0][1], 8080)

    def test_desktop_hide_coach_through_synced_wrapper(self):
        # Кнопка «🙈 Скрыть» в окне тренеров зовёт db.set_coach_hidden(cid, True)
        # (synced wrapper) — проверяем, что is_hidden=True доезжает до сервера.
        app.sync_manager = self.mgr
        cid = app._original_add_coach(
            self.db, "Иванов Иван", club="Алга", phone="+77771112233")
        self.mgr.state.map_set("coach", cid, 4242)
        self.db.set_coach_hidden(cid, True)
        succeeded, remaining = self._flush()
        self.assertEqual(remaining, 0)
        self.assertEqual(succeeded, 1)
        update_calls = [c for c in self.api.calls if c[0] == "update_coach"]
        self.assertEqual(len(update_calls), 1)
        _, remote_id, kw = update_calls[0]
        self.assertEqual(remote_id, 4242)
        self.assertTrue(kw["is_hidden"])
        self.assertEqual(kw["phone"], "+77771112233")

    def test_desktop_show_coach_through_synced_wrapper(self):
        # Кнопка «👁 Показать» зовёт db.set_coach_hidden(cid, False) — на
        # сервер уходит is_hidden=False.
        app.sync_manager = self.mgr
        cid = app._original_add_coach(self.db, "Иванов Иван")
        self.mgr.state.map_set("coach", cid, 4242)
        self.db.set_coach_hidden(cid, False)
        succeeded, remaining = self._flush()
        self.assertEqual(remaining, 0)
        self.assertEqual(succeeded, 1)
        update_calls = [c for c in self.api.calls if c[0] == "update_coach"]
        self.assertEqual(len(update_calls), 1)
        self.assertFalse(update_calls[0][2]["is_hidden"])

    def test_desktop_hide_athlete_through_synced_wrapper(self):
        app.sync_manager = self.mgr
        aid = app._original_add_athlete(
            self.db, "Петров", "Пётр", "01.01.2000", "M", club="Алга",
            phone="+77772223344")
        self.mgr.state.map_set("athlete", aid, 8080)
        self.db.set_athlete_hidden(aid, True)
        succeeded, remaining = self._flush()
        self.assertEqual(remaining, 0)
        self.assertEqual(succeeded, 1)
        update_calls = [c for c in self.api.calls if c[0] == "update_athlete"]
        self.assertEqual(len(update_calls), 1)
        self.assertTrue(update_calls[0][2]["is_hidden"])


class PullSyncHiddenTest(unittest.TestCase):
    """Pull-синк скрытых карточек (сайт -> десктоп)."""

    def setUp(self):
        self.tmp = TempDb()
        self.db = self.tmp.make_database()
        self.api = FakeApi()
        self.state = SyncState(self.tmp.state_path)
        self.mgr = PullSyncManager(
            api_client=self.api, state=self.state, db_path=self.tmp.tournament_path)
        self.conn = self.db.conn

    def tearDown(self):
        self.state.close()
        self.conn.close()
        self.tmp.cleanup()

    def test_pull_hidden_coach_does_not_create_local_card(self):
        self.mgr._upsert_coach(self.conn, {
            "id": 555, "is_hidden": True, "full_name": "Скрытый Тренер",
        })
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM coaches WHERE full_name='Скрытый Тренер'").fetchone()
        self.assertIsNone(row)
        self.assertIsNone(self.state.map_get_local("coach", 555))

    def test_pull_hidden_coach_cleans_existing_bindings(self):
        cid = self.db.add_coach("Скрытый Тренер", club="Алга",
                                club_id=self.club_id_created())
        aid = self.db.add_athlete(
            "Петров", "Пётр", "01.01.2000", "M", club="Алга",
            coach_id=cid, club_id=self.club_id_created())
        self.state.map_set("coach", cid, 555)
        self.mgr._upsert_coach(self.conn, {
            "id": 555, "is_hidden": True, "full_name": "Скрытый Тренер",
        })
        self.conn.commit()
        c = self.conn.execute("SELECT * FROM coaches WHERE id=?", (cid,)).fetchone()
        self.assertEqual(c["is_hidden"], 1)
        self.assertIsNone(c["club_id"])
        a = self.conn.execute("SELECT * FROM athletes WHERE id=?", (aid,)).fetchone()
        self.assertIsNone(a["coach_id"])

    def club_id_created(self):
        row = self.conn.execute("SELECT id FROM clubs WHERE name='Алга'").fetchone()
        if row:
            return row["id"]
        cur = self.conn.execute("INSERT INTO clubs (name) VALUES ('Алга')")
        return cur.lastrowid

    def test_pull_hidden_athlete_cleans_bindings(self):
        cid = self.club_id_created()
        aid = self.db.add_athlete(
            "Петров", "Пётр", "01.01.2000", "M", club="Алга",
            club_id=cid)
        self.state.map_set("athlete", aid, 777)
        self.mgr._upsert_athlete(self.conn, {
            "id": 777, "is_hidden": True, "full_name": "Петров Пётр",
            "gender": "M", "birth_date": "2000-01-01", "club_name": "Алга",
            "coach_name": None,
        })
        self.conn.commit()
        a = self.conn.execute("SELECT * FROM athletes WHERE id=?", (aid,)).fetchone()
        self.assertEqual(a["is_hidden"], 1)
        self.assertIsNone(a["club_id"])
        self.assertIsNone(a["coach_id"])
        self.assertIsNone(a["club"])


class CursorSelfHealTest(unittest.TestCase):
    """Инкрементальный курсор может «перескочить» мимо записей (курсор
    ставится по server_time — моменту запроса; запись, изменённая на сервере
    до этого момента, но ещё не отданная, теряется навсегда). Лечим
    периодическим полным ресинком (since=эпоха) + курсором от максимального
    updated_at доставленных записей."""

    class _ChangesApi:
        """Имитация GET /coaches/changes: with since=None/эпоха отдаёт всех,
        with since=текущий курсор — только тех, кто новее."""

        def __init__(self, coaches):
            self.coaches = coaches
            self.server_time = "2099-01-01T00:00:00+00:00"

        def get_clubs(self):
            return []

        def get_coach_changes(self, since):
            since_dt = None
            if since:
                since_dt = datetime.fromisoformat(since)
            updated = [
                c for c in self.coaches
                if since_dt is None
                or datetime.fromisoformat(c["updated_at"]) > since_dt
            ]
            return {"updated": updated, "deleted": [], "server_time": self.server_time}

        def get_athlete_changes(self, since):
            return {"updated": [], "deleted": [], "server_time": self.server_time}

    @staticmethod
    def _coach(rid, ts):
        return {
            "id": rid, "updated_at": ts, "is_hidden": False,
            "full_name": f"Тренер {rid}", "club": "Алга",
        }

    def setUp(self):
        self.tmp = TempDb()
        self.db = self.tmp.make_database()
        self.api = self._ChangesApi([
            self._coach(1, "2026-08-04T04:00:00+00:00"),
            self._coach(2, "2026-08-04T04:01:00+00:00"),
            self._coach(3, "2026-08-04T04:02:00+00:00"),
        ])
        self.state = SyncState(self.tmp.state_path)
        self.mgr = PullSyncManager(
            api_client=self.api, state=self.state, db_path=self.tmp.tournament_path)
        self.conn = self.db.conn

    def tearDown(self):
        self.state.close()
        self.conn.close()
        self.tmp.cleanup()

    def _local_coaches(self):
        return self.conn.execute("SELECT * FROM coaches").fetchall()

    def test_drifted_cursor_heals_on_full_resync(self):
        # Курсор «перескочил» мимо всех записей (см. баг с 5 тренерами
        # на сайте против 3 в десктопе): обычный опрос ничего не вернёт.
        self.state.set_cursor("coaches", "2026-08-04T04:03:00+00:00")
        self.assertEqual(self.mgr._poll_coaches(self.conn), 0)
        self.assertEqual(len(self._local_coaches()), 0)

        # Полный ресинк (раз в N опросов) идёт по since=эпоха — догоняет всех.
        self.mgr._force_full = True
        applied = self.mgr._poll_coaches(self.conn)
        self.assertEqual(applied, 3)
        coaches = self._local_coaches()
        self.assertEqual(len(coaches), 3)
        for row in coaches:
            self.assertIsNotNone(self.state.map_get("coach", row["id"]))

        # Курсор ставится по максимальному updated_at доставленного, а не по
        # server_time — иначе дрейф воспроизводится на следующем опросе.
        self.assertEqual(
            self.state.get_cursor("coaches"), "2026-08-04T04:02:00+00:00")

    def test_cursor_advances_to_max_delivered_not_server_time(self):
        # Первый опрос (since=None) тянет всех; курсор = max updated_at, а не
        # server_time (2099) — повторно всю таблицу не перетягиваем.
        self.assertEqual(self.mgr._poll_coaches(self.conn), 3)
        self.assertEqual(
            self.state.get_cursor("coaches"), "2026-08-04T04:02:00+00:00")
        self.assertEqual(self.mgr._poll_coaches(self.conn), 0)

    def test_sync_now_full_resync_pulls_skipped_records(self):
        # Кнопка «Синхронизировать» = sync_now(): полный ресинк (since=эпоха)
        # даже при «перескочившем» вперёд курсоре — все записи доедут.
        self.state.set_cursor("coaches", "2026-08-04T04:03:00+00:00")
        self.assertEqual(self.mgr.sync_now(), 3)
        coaches = self._local_coaches()
        self.assertEqual(len(coaches), 3)
        for row in coaches:
            self.assertIsNotNone(self.state.map_get("coach", row["id"]))
        self.assertEqual(
            self.state.get_cursor("coaches"), "2026-08-04T04:02:00+00:00")


if __name__ == "__main__":
    unittest.main(verbosity=2)
