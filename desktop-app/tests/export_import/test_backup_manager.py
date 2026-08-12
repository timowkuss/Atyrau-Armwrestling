"""BackupManager: авто-бэкапы, минимальный интервал, ротация (10 файлов),
аварийный экспорт, latest_backup, проверка целостности."""

import os
import shutil
import time
import unittest

from tests.export_import.helpers import Laptop2, Scenario  # noqa: E402

from transfer.backup_manager import BackupManager  # noqa: E402
from transfer.pack import read_archive  # noqa: E402


class TestBackupManager(unittest.TestCase):

    def setUp(self):
        self.sc = Scenario(finished=False)
        self.backup_dir = os.path.join(self.sc.tmp, "backups")
        self.bm = BackupManager(conn=self.sc.db.conn, state=self.sc.state,
                                backup_dir=self.backup_dir, keep=10,
                                min_interval=45)

    def tearDown(self):
        shutil.rmtree(self.sc.tmp, ignore_errors=True)

    def test_request_backup_then_tick(self):
        """request_backup + тикер maybe_autobackup создаёт файл."""
        self.bm.request_backup()
        self.bm._last_backup_at = 0.0
        created = self.bm.maybe_autobackup(self.sc.tid)
        self.assertTrue(created)
        self.assertEqual(self.bm.backup_count(), 1)

    def test_no_backup_without_request(self):
        created = self.bm.maybe_autobackup(self.sc.tid)
        self.assertFalse(created)
        self.assertEqual(self.bm.backup_count(), 0)

    def test_min_interval_gate(self):
        """§31: чаще min_interval бэкап не пишется."""
        self.bm.request_backup()
        self.bm._last_backup_at = 0.0
        self.assertTrue(self.bm.maybe_autobackup(self.sc.tid))
        self.bm.request_backup()
        self.assertFalse(self.bm.maybe_autobackup(self.sc.tid))
        self.assertEqual(self.bm.backup_count(), 1)

    def test_autobackup_now_immediate(self):
        self.bm.autobackup_now(self.sc.tid)
        self.assertEqual(self.bm.backup_count(), 1)

    def test_rotation_keeps_last_10(self):
        seq = iter(range(1, 20))
        import transfer.backup_manager as bm_mod
        orig_ts = bm_mod._ts_now
        bm_mod._ts_now = lambda: f"2026_08_11_10-00-{next(seq):02d}"
        try:
            for _ in range(15):
                self.bm.autobackup_now(self.sc.tid)
        finally:
            bm_mod._ts_now = orig_ts
        self.assertEqual(self.bm.backup_count(), 10)

    def test_autobackup_filenames_unique(self):
        """Два бэкапа подряд не затирают друг друга."""
        p1 = self.bm.autobackup_now(self.sc.tid)
        import transfer.backup_manager as bm_mod
        orig_ts = bm_mod._ts_now
        bm_mod._ts_now = lambda: "2026_08_11_10-00-59"
        try:
            p2 = self.bm.autobackup_now(self.sc.tid)
        finally:
            bm_mod._ts_now = orig_ts
        self.assertNotEqual(p1, p2)
        self.assertTrue(os.path.exists(p1) and os.path.exists(p2))

    def test_emergency_export(self):
        path = self.bm.emergency_export(self.sc.tid)
        self.assertTrue(os.path.exists(path))
        self.assertIn("emergency", os.path.basename(path))
        payload, md = read_archive(path)
        self.assertEqual(payload["competition.json"]["tournament"]["id"],
                         self.sc.tid)

    def test_latest_backup(self):
        self.assertIsNone(self.bm.latest_backup())
        self.bm.autobackup_now(self.sc.tid)
        info = self.bm.latest_backup()
        self.assertIsNotNone(info)
        self.assertTrue(os.path.exists(info["path"]))
        self.assertGreaterEqual(info["age"], 0)

    def test_check_integrity_ok(self):
        ok, msg = self.bm.check_integrity()
        self.assertTrue(ok, msg)

    def test_check_integrity_broken_db(self):
        """Реально повреждённый файл БД (битый заголовок) фиксируется."""
        import sqlite3
        path = os.path.join(self.sc.tmp, "broken.db")
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()
        import random
        rng = random.Random(1)
        with open(path, "r+b") as f:
            data = bytearray(f.read())
            for _ in range(200):
                data[rng.randrange(len(data))] ^= 0xFF
            f.seek(0)
            f.write(bytes(data))
        conn2 = sqlite3.connect(path)
        try:
            bm = BackupManager(conn=conn2, backup_dir=self.backup_dir)
            ok, _ = bm.check_integrity()
            self.assertFalse(ok)
        finally:
            conn2.close()

    def test_backup_file_is_valid_archive(self):
        path = self.bm.autobackup_now(self.sc.tid)
        payload, md = read_archive(path)
        self.assertIn("matches.json", payload)
        self.assertIn("competition.json", payload)

    def test_backup_of_missing_tournament_fails(self):
        with self.assertRaises(Exception):
            self.bm.autobackup_now(7777)
