"""§32: 4) целостность матчей, 10) рейтинг не начисляется повторно,
11) идемпотентность рейтинга, 12) очередь синхронизации переезжает,
13) operation_id сохраняется, 14) целостность спортсменов,
16) целостность тренеров, 17) целостность клубов, id_map переезжает,
18) целостность соревнования при импорте."""

import os
import shutil
import unittest
import zipfile

from tests.export_import.helpers import Laptop2, Scenario  # noqa: E402

from transfer.exporter import collect_competition_data  # noqa: E402
from transfer.importer import ImportValidationError  # noqa: E402
from transfer.pack import read_archive  # noqa: E402


class TestSyncQueuePreserved(unittest.TestCase):
    """§32.12/13: pending-операции и их id переезжают без дублей."""

    def setUp(self):
        self.sc = Scenario()
        self.dest = os.path.join(self.sc.tmp, "src.armwrestling")
        self.sc.export(self.dest)
        self.laptop = Laptop2()
        self.laptop.import_file(self.dest)

    def tearDown(self):
        shutil.rmtree(self.sc.tmp, ignore_errors=True)
        shutil.rmtree(self.laptop.tmp, ignore_errors=True)

    def test_pending_queue_preserved(self):
        self.assertEqual(self.laptop.state.pending_count(), 1)

    def test_operation_ids_preserved(self):
        rows = self.laptop.state.conn.execute(
            "SELECT id, operation FROM pending_queue").fetchall()
        self.assertEqual([r["id"] for r in rows], [self.sc.op_tid])

    def test_foreign_operation_not_copied(self):
        ids = [r["id"] for r in self.laptop.state.conn.execute(
            "SELECT id FROM pending_queue").fetchall()]
        self.assertNotIn(self.sc.op_foreign, ids)

    def test_operation_payload_intact(self):
        row = self.laptop.state.conn.execute(
            "SELECT payload FROM pending_queue WHERE id=?",
            (self.sc.op_tid,)).fetchone()
        import json
        payload = json.loads(row["payload"])
        self.assertEqual(payload["tid"], self.sc.tid)
        self.assertEqual(payload["winner_id"], self.sc.p1)

    def test_id_map_preserved(self):
        self.assertEqual(
            self.laptop.state.map_get("competition", self.sc.tid), 9001)
        self.assertEqual(
            self.laptop.state.map_get("match", self.sc.m_done), 6001)
        self.assertEqual(
            self.laptop.state.map_get("athlete", self.sc.ath_a), 5001)
        self.assertEqual(
            self.laptop.state.map_get("club", self.sc.club_a), 3001)
        self.assertEqual(
            self.laptop.state.map_get("athlete_of_participant", self.sc.p1),
            self.sc.ath_a)

    def test_foreign_id_map_not_copied(self):
        self.sc.state.map_set("competition", 999, 1111)
        dest = os.path.join(self.sc.tmp, "src2.armwrestling")
        self.sc.export(dest)
        laptop2 = Laptop2()
        laptop2.import_file(dest)
        self.assertIsNone(laptop2.state.map_get("competition", 999))
        shutil.rmtree(laptop2.tmp, ignore_errors=True)


class TestRatingNotDuplicated(unittest.TestCase):
    """§32.10/11: при импорте завершённого турнира рейтинг НЕ начисляется
    повторно — переносятся уже применённые события, сумма не меняется."""

    def setUp(self):
        self.sc = Scenario()
        self.dest = os.path.join(self.sc.tmp, "src.armwrestling")
        self.sc.export(self.dest)
        self.laptop = Laptop2()
        self.laptop.import_file(self.dest)

    def tearDown(self):
        shutil.rmtree(self.sc.tmp, ignore_errors=True)
        shutil.rmtree(self.laptop.tmp, ignore_errors=True)

    def test_rating_sums_equal_history(self):
        for conn in (self.sc.db.conn, self.laptop.db.conn):
            rating = dict(conn.execute(
                "SELECT club_id, rating FROM club_rating").fetchall())
            history_sum = dict(conn.execute(
                "SELECT club_id, SUM(points) AS s FROM club_rating_history "
                "GROUP BY club_id").fetchall())
            for club_id, points in history_sum.items():
                self.assertEqual(rating.get(club_id), points,
                                 "rating должен равняться сумме событий")

    def test_rating_history_imported_exactly_once(self):
        src_count = self.sc.db.conn.execute(
            "SELECT COUNT(*) FROM club_rating_history WHERE tournament_id=?",
            (self.sc.tid,)).fetchone()[0]
        dst_count = self.laptop.db.conn.execute(
            "SELECT COUNT(*) FROM club_rating_history WHERE tournament_id=?",
            (self.sc.tid,)).fetchone()[0]
        self.assertEqual(src_count, dst_count)
        self.assertGreater(src_count, 0)

    def test_no_new_events_after_import(self):
        """Импорт не добавляет событий: идемпотентность индекса
        (club_id, athlete_id, tournament_id, reason, description)."""
        before = self.laptop.db.conn.execute(
            "SELECT COUNT(*) FROM club_rating_history WHERE tournament_id=?",
            (self.sc.tid,)).fetchone()[0]
        self.laptop.import_file(self.dest, force_replace=True)
        after = self.laptop.db.conn.execute(
            "SELECT COUNT(*) FROM club_rating_history WHERE tournament_id=?",
            (self.sc.tid,)).fetchone()[0]
        self.assertEqual(before, after)

    def test_rating_idempotency_reimport(self):
        """Повторный force_replace не задваивает события и очки."""
        r1 = self.laptop.db.conn.execute(
            "SELECT rating FROM club_rating WHERE club_id=?",
            (self.sc.club_a,)).fetchone()[0]
        self.laptop.import_file(self.dest, force_replace=True)
        r2 = self.laptop.db.conn.execute(
            "SELECT rating FROM club_rating WHERE club_id=?",
            (self.sc.club_a,)).fetchone()[0]
        self.assertEqual(r1, r2)


class TestValidationAtImport(unittest.TestCase):
    """§32.14/16/17/18: импорт отклоняет нарушенные ссылки."""

    def setUp(self):
        self.sc = Scenario()
        self.dest = os.path.join(self.sc.tmp, "src.armwrestling")
        self.sc.export(self.dest)

    def tearDown(self):
        shutil.rmtree(self.sc.tmp, ignore_errors=True)

    def _build_bad(self, mutate):
        bad = os.path.join(self.sc.tmp, "bad.armwrestling")
        with zipfile.ZipFile(self.dest) as z:
            names = z.namelist()
            contents = {n: z.read(n) for n in names}
        import json
        payload = {n.replace(".json", ""):
                   json.loads(contents[n].decode("utf-8"))
                   for n in names if n.endswith(".json")}
        mutate(payload)
        out = {}
        for n in names:
            if n.endswith(".json") and n != "metadata.json":
                key = n.replace(".json", "")
                out[n] = json.dumps(
                    payload[key], ensure_ascii=False).encode("utf-8")
        from transfer.pack import compute_checksum
        md = json.loads(contents["metadata.json"].decode("utf-8"))
        md["checksum"] = compute_checksum(out)
        contents["metadata.json"] = json.dumps(
            md, ensure_ascii=False).encode("utf-8")
        for n, data in out.items():
            contents[n] = data
        with zipfile.ZipFile(bad, "w") as z:
            for n in contents:
                z.writestr(n, contents[n])
        return bad

    def _assert_import_rejected(self, bad):
        laptop = Laptop2()
        try:
            with self.assertRaises(ImportValidationError):
                laptop.import_file(bad)
        finally:
            shutil.rmtree(laptop.tmp, ignore_errors=True)

    def test_match_category_reference(self):
        """§32.4: матч без категории → отказ."""
        bad = self._build_bad(lambda p: p["matches"][0].update(category_id=9999))
        self._assert_import_rejected(bad)

    def test_match_participant_reference(self):
        bad = self._build_bad(lambda p: p["matches"][0].update(p1_id=5555))
        self._assert_import_rejected(bad)

    def test_match_winner_in_match(self):
        bad = self._build_bad(lambda p: p["matches"][0].update(winner_id=7777))
        self._assert_import_rejected(bad)

    def test_participant_category_reference(self):
        bad = self._build_bad(
            lambda p: p["participants"][0].update(category_id=9999))
        self._assert_import_rejected(bad)

    def test_athlete_reference(self):
        """§32.14: участник ссылается на несуществующего спортсмена."""
        bad = self._build_bad(
            lambda p: p["participants"][0].update(athlete_id=9999))
        self._assert_import_rejected(bad)

    def test_coach_reference(self):
        """§32.16: спортсмен ссылается на несуществующего тренера."""
        bad = self._build_bad(
            lambda p: p["athletes"][0].update(coach_id=9999))
        self._assert_import_rejected(bad)

    def test_club_reference(self):
        """§32.17: спортсмен/тренер ссылается на несуществующий клуб."""
        bad = self._build_bad(
            lambda p: p["athletes"][0].update(club_id=9999))
        self._assert_import_rejected(bad)

    def test_rating_history_athlete_reference(self):
        history = self._build_bad(
            lambda p: p["rating_events"]["history"][0].update(athlete_id=9999))
        self._assert_import_rejected(history)

    def test_results_matches_done(self):
        """§32.4: снапшот результатов содержит только status='done'."""
        payload, _ = read_archive(self.dest)
        done_ids = {m["id"] for m in payload["matches.json"]
                    if m["status"] == "done"}
        result_ids = {r["match_id"] for r in payload["results.json"]}
        self.assertEqual(done_ids, result_ids)

    def test_duplicate_participant_ids(self):
        bad = self._build_bad(
            lambda p: p["participants"].append(dict(p["participants"][0])))
        self._assert_import_rejected(bad)

    def test_valid_archive_passes_validation(self):
        from transfer.importer import validate_archive
        payload, metadata = read_archive(self.dest)
        validate_archive(payload, metadata)
