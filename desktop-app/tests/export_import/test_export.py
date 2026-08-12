"""§32: 1) экспорт соревнования, 3) экспорт без интернета,
5) битый файл, 15) повреждённый checksum, 18) целостность соревнования,
19) проверка версий, 21) пароль, лишний файл в архиве."""

import os
import sqlite3
import unittest
import zipfile

from tests.export_import.helpers import BASE, Scenario  # noqa: E402

from transfer.exporter import (  # noqa: E402
    ExportError,
    collect_competition_data,
    export_competition,
    validate_competition_integrity,
)
from transfer.pack import (  # noqa: E402
    BackupFormatError,
    EXPORT_VERSION,
    read_archive,
)


class TestExportCompetition(unittest.TestCase):
    """§32.1 Экспорт соревнования: создаётся файл, читается, разделы полны."""

    def setUp(self):
        self.sc = Scenario()

    def tearDown(self):
        for path in (self.sc.tmp,):
            import shutil
            shutil.rmtree(path, ignore_errors=True)

    def test_export_creates_valid_archive(self):
        dest = os.path.join(self.sc.tmp, "out.armwrestling")
        metadata = self.sc.export(dest)
        self.assertTrue(os.path.exists(dest))
        self.assertEqual(metadata["competition_id"], self.sc.tid)
        self.assertEqual(metadata["export_version"], EXPORT_VERSION)
        self.assertEqual(metadata["counts"]["matches"], 2)
        self.assertEqual(metadata["counts"]["finished_matches"], 1)
        self.assertEqual(metadata["counts"]["unfinished_matches"], 1)
        payload, md = read_archive(dest)
        self.assertEqual(len(payload["matches.json"]), 2)
        self.assertEqual(len(payload["participants.json"]), 2)
        self.assertEqual(len(payload["athletes.json"]), 2)
        self.assertEqual(len(payload["clubs.json"]), 2)
        self.assertEqual(len(payload["coaches.json"]), 1)

    def test_export_offline(self):
        """§32.3 Экспорт не требует сети и не блокируется её отсутствием:
        заглушка _NoSync уже означает «нет сети» — экспорт проходит."""
        dest = os.path.join(self.sc.tmp, "offline.armwrestling")
        metadata = self.sc.export(dest)
        self.assertTrue(os.path.exists(dest))
        self.assertEqual(metadata["counts"]["matches"], 2)

    def test_export_validation_problems_empty(self):
        """§32.18 validate_competition_integrity на корректных данных — []."""
        problems = validate_competition_integrity(self.sc.db.conn, self.sc.tid)
        self.assertEqual(problems, [])

    def test_export_integrity_problem_participant_without_category(self):
        db = self.sc.db
        db.conn.execute("UPDATE participants SET category_id=9999 "
                        "WHERE id=?", (self.sc.p1,))
        db.conn.commit()
        problems = validate_competition_integrity(db.conn, self.sc.tid)
        self.assertTrue(any("категори" in p.lower() for p in problems))
        with self.assertRaises(ExportError):
            self.sc.export(os.path.join(self.sc.tmp, "x.armwrestling"))

    def test_export_integrity_problem_match_winner_not_in_match(self):
        db = self.sc.db
        db.conn.execute("UPDATE matches SET winner_id=7777 WHERE id=?",
                        (self.sc.m_done,))
        db.conn.commit()
        problems = validate_competition_integrity(db.conn, self.sc.tid)
        self.assertTrue(problems)
        with self.assertRaises(ExportError):
            self.sc.export(os.path.join(self.sc.tmp, "x.armwrestling"))

    def test_export_emergency_skips_check(self):
        """Аварийный экспорт проходит даже с битыми данными."""
        db = self.sc.db
        db.conn.execute("UPDATE participants SET category_id=9999 "
                        "WHERE id=?", (self.sc.p1,))
        db.conn.commit()
        dest = os.path.join(self.sc.tmp, "emerg.armwrestling")
        metadata = self.sc.export(dest, emergency=True)
        self.assertTrue(os.path.exists(dest))
        payload, _ = read_archive(dest)
        self.assertEqual(payload["competition.json"]["tournament"]["id"],
                         self.sc.tid)


class TestCorruptedFiles(unittest.TestCase):
    """§32.5 Битый файл / 15. Checksum / лишние файлы / 19. Версии."""

    def setUp(self):
        self.sc = Scenario()
        self.dest = os.path.join(self.sc.tmp, "ok.armwrestling")
        self.sc.export(self.dest)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.sc.tmp, ignore_errors=True)

    def test_not_a_zip(self):
        bad = os.path.join(self.sc.tmp, "notzip.armwrestling")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("это не архив")
        from transfer.importer import preview_archive
        with self.assertRaises(BackupFormatError):
            preview_archive(bad)

    def test_corrupted_zip(self):
        bad = os.path.join(self.sc.tmp, "corrupt.armwrestling")
        with open(self.dest, "rb") as f:
            data = f.read()
        data = data[:len(data) // 2]
        with open(bad, "wb") as f:
            f.write(data)
        from transfer.importer import preview_archive
        with self.assertRaises(BackupFormatError):
            preview_archive(bad)

    def test_extra_member_detected(self):
        bad = os.path.join(self.sc.tmp, "extra.armwrestling")
        with zipfile.ZipFile(self.dest) as z:
            names = z.namelist()
            contents = {n: z.read(n) for n in names}
        with zipfile.ZipFile(bad, "w") as z:
            for n in contents:
                z.writestr(n, contents[n])
            z.writestr("hack.txt", "взлом")
        from transfer.importer import preview_archive
        with self.assertRaises(BackupFormatError):
            preview_archive(bad)

    def test_checksum_mismatch(self):
        """§32.15: изменение содержимого раздела даёт несовпадение checksum."""
        bad = os.path.join(self.sc.tmp, "tampered.armwrestling")
        with zipfile.ZipFile(self.dest) as z:
            names = z.namelist()
            contents = {n: z.read(n) for n in names}
        orig = contents["matches.json"]
        contents["matches.json"] = orig.replace(
            "Правая".encode("utf-8"), "Левая".encode("utf-8"))
        with zipfile.ZipFile(bad, "w") as z:
            for n in contents:
                z.writestr(n, contents[n])
        from transfer.importer import preview_archive
        with self.assertRaises(BackupFormatError):
            preview_archive(bad)

    def test_metadata_tamper_no_checksum(self):
        bad = os.path.join(self.sc.tmp, "nochecksum.armwrestling")
        with zipfile.ZipFile(self.dest) as z:
            names = z.namelist()
            contents = {n: z.read(n) for n in names}
        import json
        md = json.loads(contents["metadata.json"].decode("utf-8"))
        md.pop("checksum")
        contents["metadata.json"] = json.dumps(
            md, ensure_ascii=False).encode("utf-8")
        with zipfile.ZipFile(bad, "w") as z:
            for n in contents:
                z.writestr(n, contents[n])
        from transfer.importer import preview_archive
        with self.assertRaises(BackupFormatError):
            preview_archive(bad)

    def test_newer_version_rejected(self):
        """§32.19: файл более новой версии не импортируется."""
        bad = os.path.join(self.sc.tmp, "newver.armwrestling")
        with zipfile.ZipFile(self.dest) as z:
            names = z.namelist()
            contents = {n: z.read(n) for n in names}
        import json
        md = json.loads(contents["metadata.json"].decode("utf-8"))
        md["export_version"] = EXPORT_VERSION + 1
        # checksum тоже надо обновить — иначе упадёт раньше; но тестируем
        # именно проверку версии, поэтому чиним checksum.
        from transfer.pack import compute_checksum
        raw = {n: c for n, c in contents.items() if n != "metadata.json"}
        md["checksum"] = compute_checksum(raw)
        contents["metadata.json"] = json.dumps(
            md, ensure_ascii=False).encode("utf-8")
        with zipfile.ZipFile(bad, "w") as z:
            for n in contents:
                z.writestr(n, contents[n])
        from transfer.importer import preview_archive
        with self.assertRaises(BackupFormatError):
            preview_archive(bad)


class TestPassword(unittest.TestCase):
    """§32.21: защита паролем — без пароля не открыть, с неверным — тоже."""

    def setUp(self):
        self.sc = Scenario()
        self.dest = os.path.join(self.sc.tmp, "locked.armwrestling")
        self.sc.export(self.dest, password="секрет123")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.sc.tmp, ignore_errors=True)

    def test_password_required(self):
        from transfer.importer import preview_archive
        with self.assertRaises(BackupFormatError):
            preview_archive(self.dest)

    def test_wrong_password(self):
        from transfer.importer import preview_archive
        with self.assertRaises(BackupFormatError):
            preview_archive(self.dest, password="неверный")

    def test_correct_password(self):
        from transfer.importer import preview_archive
        metadata, summary = preview_archive(self.dest, password="секрет123")
        self.assertEqual(summary["competition_id"], self.sc.tid)

    def test_correct_password_import(self):
        laptop = None
        from tests.export_import.helpers import Laptop2
        laptop = Laptop2()
        res = laptop.import_file(self.dest, password="секрет123")
        self.assertEqual(res["competition_id"], self.sc.tid)
        import shutil
        shutil.rmtree(laptop.tmp, ignore_errors=True)


class TestCollectData(unittest.TestCase):
    """Проверка разделов архива на уровне collect_competition_data."""

    def setUp(self):
        self.sc = Scenario()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.sc.tmp, ignore_errors=True)

    def test_collect_excludes_foreign_sync_ops(self):
        data = collect_competition_data(self.sc.db.conn, self.sc.state,
                                        self.sc.tid)
        ops = data["payload"]["sync_operations.json"]
        ids = {o["id"] for o in ops}
        self.assertIn(self.sc.op_tid, ids)
        self.assertNotIn(self.sc.op_foreign, ids)

    def test_collect_excludes_foreign_id_map(self):
        self.sc.state.map_set("competition", 999, 1111)
        data = collect_competition_data(self.sc.db.conn, self.sc.state,
                                        self.sc.tid)
        keys = {(r["entity_type"], r["local_id"])
                for r in data["payload"]["id_map.json"]}
        self.assertNotIn(("competition", 999), keys)
        self.assertIn(("competition", self.sc.tid), keys)

    def test_collect_rating_history_only_own(self):
        from club_rating import add_points
        add_points(self.sc.db.conn, self.sc.club_a, None, 999,
                   5, "TEST", "чужой турнир")
        data = collect_competition_data(self.sc.db.conn, self.sc.state,
                                        self.sc.tid)
        history = data["payload"]["rating_events.json"]["history"]
        self.assertTrue(all(h["tournament_id"] == self.sc.tid for h in history))
