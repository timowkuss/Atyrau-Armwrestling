"""§32: 2) импорт соревнования, 6) повторный импорт (дубль),
7) импорт того же соревнования (force_replace), 8) частичная порча,
9) откат при ошибке, восстановление после сбоя (backup), фото."""

import os
import shutil
import sqlite3
import unittest

from tests.export_import.helpers import (  # noqa: E402
    Laptop2,
    Scenario,
    assert_snapshot_equal,
    snapshot,
)

from transfer.importer import (  # noqa: E402
    CompetitionExistsError,
    IdCollisionError,
    ImportValidationError,
    import_competition,
    preview_archive,
)
from transfer.pack import BackupFormatError  # noqa: E402


class TestImportCompetition(unittest.TestCase):
    """§32.2: импорт в свежую БД полностью воспроизводит данные."""

    def setUp(self):
        self.sc = Scenario()
        self.dest = os.path.join(self.sc.tmp, "src.armwrestling")
        self.sc.export(self.dest)
        self.laptop = Laptop2()

    def tearDown(self):
        shutil.rmtree(self.sc.tmp, ignore_errors=True)
        shutil.rmtree(self.laptop.tmp, ignore_errors=True)

    def test_roundtrip_data_equal(self):
        src_snap = snapshot(self.sc.db, self.sc.tid)
        res = self.laptop.import_file(self.dest)
        self.assertEqual(res["competition_id"], self.sc.tid)
        self.assertEqual(res["matches"], 2)
        self.assertEqual(res["finished"], 1)
        dst_snap = snapshot(self.laptop.db, self.sc.tid)
        assert_snapshot_equal(self, src_snap, dst_snap, self.sc.tid)

    def test_import_generates_new_session_id(self):
        src_session = self.sc.db.conn.execute(
            "SELECT session_id FROM tournaments WHERE id=?",
            (self.sc.tid,)).fetchone()[0]
        self.laptop.import_file(self.dest)
        dst_session = self.laptop.db.conn.execute(
            "SELECT session_id FROM tournaments WHERE id=?",
            (self.sc.tid,)).fetchone()[0]
        self.assertIsNotNone(dst_session)
        self.assertNotEqual(src_session, dst_session)

    def test_import_sets_previous_session_in_transfer_marks(self):
        src_session = self.sc.db.conn.execute(
            "SELECT session_id FROM tournaments WHERE id=?",
            (self.sc.tid,)).fetchone()[0]
        self.laptop.import_file(self.dest)
        mark = self.laptop.db.conn.execute(
            "SELECT previous_session_id FROM transfer_marks "
            "WHERE tournament_id=?", (self.sc.tid,)).fetchone()
        self.assertIsNotNone(mark)
        self.assertEqual(mark["previous_session_id"], src_session)

    def test_import_photos(self):
        photo = os.path.join(self.sc.tmp, "foto.jpg")
        with open(photo, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0photo-bytes")
        self.sc.db.conn.execute(
            "UPDATE participants SET photo_path=? WHERE id=?",
            (photo, self.sc.p1))
        self.sc.db.conn.commit()
        dest = os.path.join(self.sc.tmp, "withphoto.armwrestling")
        self.sc.export(dest, include_photos=True)
        self.laptop.import_file(dest)
        row = self.laptop.db.conn.execute(
            "SELECT photo_path FROM participants WHERE id=?",
            (self.sc.p1,)).fetchone()
        self.assertTrue(row["photo_path"])
        new_path = row["photo_path"]
        self.assertTrue(os.path.exists(new_path))
        with open(new_path, "rb") as f:
            self.assertEqual(f.read(), b"\xff\xd8\xff\xe0photo-bytes")

    def test_import_preserves_finished_tournament_rating(self):
        src_snap = snapshot(self.sc.db, self.sc.tid)
        self.assertTrue(src_snap["history"], "рейтинг должен быть начислен")
        self.laptop.import_file(self.dest)
        dst_snap = snapshot(self.laptop.db, self.sc.tid)
        self.assertEqual(src_snap["history"], dst_snap["history"])
        src_rating = dict(self.sc.db.conn.execute(
            "SELECT club_id, rating FROM club_rating").fetchall())
        dst_rating = dict(self.laptop.db.conn.execute(
            "SELECT club_id, rating FROM club_rating").fetchall())
        self.assertEqual(src_rating, dst_rating)


class TestDuplicateAndReplace(unittest.TestCase):
    """§32.6 дубликат / §32.7 замена существующего."""

    def setUp(self):
        self.sc = Scenario()
        self.dest = os.path.join(self.sc.tmp, "src.armwrestling")
        self.sc.export(self.dest)
        self.laptop = Laptop2()
        self.laptop.import_file(self.dest)

    def tearDown(self):
        shutil.rmtree(self.sc.tmp, ignore_errors=True)
        shutil.rmtree(self.laptop.tmp, ignore_errors=True)

    def test_duplicate_import_refused(self):
        with self.assertRaises(CompetitionExistsError):
            self.laptop.import_file(self.dest)

    def test_force_replace_ok(self):
        res = self.laptop.import_file(self.dest, force_replace=True)
        self.assertEqual(res["matches"], 2)

    def test_force_replace_removes_local_extra_data(self):
        db = self.laptop.db
        extra = db.add_participant(self.sc.tid, "Лишний", 75.0, "X",
                                   self.sc.cat, "Правая")
        self.assertIsNotNone(db.conn.execute(
            "SELECT id FROM participants WHERE id=?", (extra,)).fetchone())
        self.laptop.import_file(self.dest, force_replace=True)
        self.assertIsNone(db.conn.execute(
            "SELECT id FROM participants WHERE id=?", (extra,)).fetchone())

    def test_force_replace_same_session_flag(self):
        """Новая сессия → флаг «другая сессия» в CompetitionExistsError."""
        db = self.laptop.db
        db.conn.execute("UPDATE tournaments SET session_id='other-session' "
                        "WHERE id=?", (self.sc.tid,))
        db.conn.commit()
        try:
            self.laptop.import_file(self.dest)
            self.fail("ожидался CompetitionExistsError")
        except CompetitionExistsError as e:
            self.assertTrue(e.other_session)

    def test_import_does_not_touch_other_competitions(self):
        other = self.laptop.db.create_tournament("Other", "01.01.2026", "X")
        self.laptop.import_file(self.dest, force_replace=True)
        row = self.laptop.db.conn.execute(
            "SELECT name FROM tournaments WHERE id=?", (other,)).fetchone()
        self.assertEqual(row["name"], "Other")


class TestImportFailures(unittest.TestCase):
    """§32.8 частичная порча / §32.9 откат транзакции."""

    def setUp(self):
        self.sc = Scenario()
        self.dest = os.path.join(self.sc.tmp, "src.armwrestling")
        self.sc.export(self.dest)
        self.laptop = Laptop2()

    def tearDown(self):
        shutil.rmtree(self.sc.tmp, ignore_errors=True)
        shutil.rmtree(self.laptop.tmp, ignore_errors=True)

    def _tamper(self, member, new_content):
        import zipfile
        bad = os.path.join(self.sc.tmp, "bad.armwrestling")
        with zipfile.ZipFile(self.dest) as z:
            names = z.namelist()
            contents = {n: z.read(n) for n in names}
        contents[member] = new_content
        with zipfile.ZipFile(bad, "w") as z:
            for n in contents:
                z.writestr(n, contents[n])
        return bad

    def test_corrupt_json_section_rejected(self):
        bad = self._tamper("matches.json", "[не json".encode("utf-8"))
        with self.assertRaises(BackupFormatError):
            preview_archive(bad)

    def test_import_partial_failure_db_unchanged(self):
        """Повреждённый раздел — предпросмотр падает, БД не трогается."""
        bad = self._tamper("matches.json", b"[]")
        with self.assertRaises(BackupFormatError):
            preview_archive(bad)
        rows = self.laptop.db.conn.execute(
            "SELECT COUNT(*) AS c FROM tournaments").fetchone()["c"]
        self.assertEqual(rows, 0)

    def test_import_rollback_on_id_collision(self):
        """§32.9: конфликт id спортсмена → ошибка, БД остаётся пустой."""
        from transfer.pack import read_archive
        payload, _ = read_archive(self.dest)
        athletes = payload["athletes.json"]
        self.assertTrue(athletes)
        db = self.laptop.db
        db.conn.execute(
            "INSERT INTO athletes (id, first_name, last_name, birth_date, "
            "gender) VALUES (?, 'Чужой', 'Чужой', '2000-01-01', 'M')",
            (athletes[0]["id"],))
        db.conn.commit()
        with self.assertRaises(IdCollisionError):
            self.laptop.import_file(self.dest)
        count = db.conn.execute(
            "SELECT COUNT(*) AS c FROM tournaments").fetchone()["c"]
        self.assertEqual(count, 0)

    def test_import_validation_error_leaves_no_partial_rows(self):
        """Порча данных, прошедшая checksum? Невозможна при честном файле —
        проверяем, что падение в середине записи откатывает всё."""
        import zipfile
        bad = os.path.join(self.sc.tmp, "badmid.armwrestling")
        with zipfile.ZipFile(self.dest) as z:
            names = z.namelist()
            contents = {n: z.read(n) for n in names}
        import json
        payload = json.loads(contents["participants.json"].decode("utf-8"))
        payload.append({"id": 1, "tournament_id": self.sc.tid,
                        "name": "Дубль id=1"})
        contents["participants.json"] = json.dumps(
            payload, ensure_ascii=False).encode("utf-8")
        from transfer.pack import compute_checksum
        raw = {n: c for n, c in contents.items() if n != "metadata.json"}
        md = json.loads(contents["metadata.json"].decode("utf-8"))
        md["checksum"] = compute_checksum(raw)
        contents["metadata.json"] = json.dumps(
            md, ensure_ascii=False).encode("utf-8")
        with zipfile.ZipFile(bad, "w") as z:
            for n in contents:
                z.writestr(n, contents[n])
        with self.assertRaises(ImportValidationError):
            self.laptop.import_file(bad)
        count = self.laptop.db.conn.execute(
            "SELECT COUNT(*) AS c FROM tournaments").fetchone()["c"]
        self.assertEqual(count, 0)

    def test_import_never_partially_commits_sync_state(self):
        from transfer.pack import read_archive
        payload, _ = read_archive(self.dest)
        self.laptop.db.conn.execute(
            "INSERT INTO clubs (id, name) VALUES (?, 'Занят')",
            (payload["clubs.json"][0]["id"],))
        self.laptop.db.conn.commit()
        with self.assertRaises(IdCollisionError):
            self.laptop.import_file(self.dest)
        self.assertEqual(self.laptop.state.pending_count(), 0)


class TestRecoveryFromBackup(unittest.TestCase):
    """§32.20: «сбой» — экспорт-файл остаётся, восстановление импортом."""

    def setUp(self):
        self.sc = Scenario()
        self.dest = os.path.join(self.sc.tmp, "src.armwrestling")
        self.sc.export(self.dest)

    def tearDown(self):
        shutil.rmtree(self.sc.tmp, ignore_errors=True)

    def test_recovery_after_crash(self):
        """Имитация сбоя: вторая БД не создаётся, есть только файл backup.
        Восстановление = импорт файла в свежую БД."""
        src_snap = snapshot(self.sc.db, self.sc.tid)
        laptop = Laptop2()
        res = laptop.import_file(self.dest)
        self.assertEqual(res["finished"], 1)
        dst_snap = snapshot(laptop.db, self.sc.tid)
        assert_snapshot_equal(self, src_snap, dst_snap, self.sc.tid)
        shutil.rmtree(laptop.tmp, ignore_errors=True)
