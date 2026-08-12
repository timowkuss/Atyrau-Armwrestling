"""Стресс-тесты экспорта/импорта соревнования.

Сценарии:
- большой турнир (сотни участников, тысячи матчей, тысячи операций sync,
  большая id_map, много спортивных клубов/истории рейтинга);
- цепочка переносов «ноутбук 1 → ноутбук 2 → ноутбук 3» — данные не
  деградируют через несколько импортов;
- повторный force_replace на больших данных — без дублей, рейтинг
  идемпотентен;
- много фотографий (в т.ч. с паролем);
- порча большого файла в разных местах — импорт всегда отклоняется чисто;
- производительность: импорт/экспорт большого турнира укладываются в
  разумное время.
"""

import json
import os
import random
import shutil
import time
import unittest
import zipfile

from tests.export_import.helpers import (  # noqa: E402
    Laptop2,
    Scenario,
    assert_snapshot_equal,
    snapshot,
)

from transfer.importer import (  # noqa: E402
    CompetitionExistsError,
    ImportValidationError,
    import_competition,
    preview_archive,
)
from transfer.pack import (  # noqa: E402
    BackupFormatError,
    read_archive,
)
from transfer.exporter import (  # noqa: E402
    ExportError,
    export_competition,
    validate_competition_integrity,
)


def make_big_scenario(participants=400, match_factor=3, pending_ops=2000,
                      extra_foreign_ops=500, extra_foreign_map=500,
                      rng_seed=7):
    """«Настоящий» большой турнир через Database (то же, что и приложение):
    категории, участники со спортсменами/клубами, полный дабл-эл брэкет
    (связи win_next_id/lose_next_id), история рейтинга, очередь и id_map."""
    import os
    import tempfile
    import sys
    from tests.export_import import helpers as H
    import armwrestling_tournament as app
    import club_rating
    from sync.state import SyncState

    rng = random.Random(rng_seed)
    tmp = tempfile.mkdtemp(prefix="armw_stress_")
    app.sync_manager = H._NoSync()
    app.DB_PATH = os.path.join(tmp, "big.db")
    app.PHOTOS_DIR = os.path.join(tmp, "photos")
    os.makedirs(app.PHOTOS_DIR, exist_ok=True)
    db = app.Database()
    state = SyncState(os.path.join(tmp, "big_sync.db"))

    tid = db.create_tournament("Big Cup 2026", "15.08.2026", "Big City")
    clubs = {i: db.add_club(f"Club {i}", f"City {i % 10}") for i in range(1, 31)}
    athletes = {}
    coaches = {}
    for i in range(1, 61):
        coaches[i] = db.add_coach(f"Coach {i}", club=f"Club {i % 30 + 1}",
                                  club_id=clubs[i % 30 + 1])
    for i in range(1, 401):
        athletes[i] = db.add_athlete(f"Name{i}", f"Last{i}", "1990-01-01", "M",
                                     club=f"Club {i % 30 + 1}",
                                     coach_id=coaches[i % 60 + 1],
                                     club_id=clubs[i % 30 + 1])

    categories = {}
    for w in range(60, 200, 20):
        categories[w] = db.add_category(tid, f"{w} кг", w, "Правая")

    participant_ids = []
    for i in range(1, participants + 1):
        cat = categories[60 + (i * 20) % 140]
        pid = db.add_participant(tid, f"Спортсмен {i}", 60 + i % 100,
                                 f"Club {i % 30 + 1}", cat, "Правая",
                                 athlete_id=athletes[i % 400 + 1])
        participant_ids.append(pid)

    # Полный брэкет в каждой категории: участники раскидываются по
    # категориям остатком (вес//20)%7 — у каждой категории свой пул,
    # матчи не пересекаются между категориями.
    match_ids = []
    slot = 0
    for w, cat_id in categories.items():
        pool = [p for p in participant_ids if p % 7 == (w // 20) % 7][:128]
        if len(pool) < 2:
            continue
        cur = list(pool)
        score = 0
        while len(cur) > 1:
            nxt = []
            for j in range(0, len(cur) - 1, 2):
                slot += 1
                mid = db.save_match({
                    "tournament_id": tid, "category_id": cat_id,
                    "hand": "Правая", "round_name": f"R{score + 1}",
                    "bracket": "winners", "match_order": slot,
                    "p1_id": cur[j], "p2_id": cur[j + 1],
                    "status": "done", "winner_id": cur[j],
                    "p1_losses": 0, "p2_losses": 1, "is_bye": 0})
                match_ids.append(mid)
                nxt.append(cur[j])
            if len(cur) % 2:
                nxt.append(cur[-1])
            cur = nxt
            score += 1
            if len(cur) <= 1:
                break

    db.finish_tournament(tid)
    club_rating.finalize_competition(db.conn, tid)

    for i in range(1, pending_ops + 1):
        state.enqueue("update_match", {
            "tid": tid, "mid": (i % len(match_ids)) + 1,
            "category_id": 60 + (i * 20) % 140, "pid": i % 400 + 1,
            "winner_id": i % 400 + 1})
    for i in range(1, extra_foreign_ops + 1):
        state.enqueue("create_tournament", {"tid": 900000 + i,
                                            "name": f"Foreign {i}",
                                            "date": "01.01.2026"})
    for i in range(1, participants + 1):
        state.map_set("competition" if i == 1 else "participant",
                      tid if i == 1 else i, 100000 + i)
    state.map_set("match", match_ids[-1], 500000)
    for i in range(1, 31):
        state.map_set("club", i, 700000 + i)
    for i in range(1, extra_foreign_map + 1):
        state.map_set("competition", 900000 + i, 1 + i)
    return {"tmp": tmp, "db": db, "state": state, "tid": tid,
            "participants": participant_ids, "matches": match_ids}


class _BigFixture(unittest.TestCase):
    """Общий фикстур: большой турнир + экспортированный файл."""

    participants = 600
    pending_ops = 1500
    extra_foreign_ops = 500

    def setUp(self):
        self.big = make_big_scenario(
            participants=self.participants,
            pending_ops=self.pending_ops,
            extra_foreign_ops=self.extra_foreign_ops)
        self.tid = self.big["tid"]
        self.dest = os.path.join(self.big["tmp"], "big.armwrestling")
        t0 = time.time()
        metadata = export_competition(self.big["db"].conn,
                                      self.big["state"], self.tid,
                                      self.dest)
        self.export_seconds = time.time() - t0
        self.metadata = metadata
        self.laptop = Laptop2()

    def tearDown(self):
        shutil.rmtree(self.big["tmp"], ignore_errors=True)
        shutil.rmtree(self.laptop.tmp, ignore_errors=True)


class TestStressScale(_BigFixture):
    """Большой турнир: полное равенство данных и разумное время."""

    participants = 1200
    pending_ops = 3000

    def test_big_export_and_preview(self):
        self.assertTrue(os.path.exists(self.dest))
        payload, md = read_archive(self.dest)
        self.assertEqual(md["counts"]["participants"], self.participants)
        self.assertGreater(md["counts"]["matches"], 500)
        self.assertGreater(md["counts"]["finished_matches"], 500)
        self.assertEqual(md["counts"]["pending_operations"],
                         self.pending_ops)
        metadata, summary = preview_archive(self.dest)
        self.assertEqual(summary["matches"], md["counts"]["matches"])
        self.assertLess(self.export_seconds, 60)

    def test_big_import_roundtrip(self):
        t0 = time.time()
        res = self.laptop.import_file(self.dest)
        import_seconds = time.time() - t0
        self.assertLess(import_seconds, 60)
        self.assertEqual(res["competition_id"], self.tid)
        src_snap = snapshot(self.big["db"], self.tid)
        dst_snap = snapshot(self.laptop.db, self.tid)
        assert_snapshot_equal(self, src_snap, dst_snap, self.tid)
        self.assertEqual(self.laptop.state.pending_count(), self.pending_ops)

    def test_big_foreign_ops_not_imported(self):
        self.laptop.import_file(self.dest)
        rows = self.laptop.state.conn.execute(
            "SELECT DISTINCT payload FROM pending_queue").fetchall()
        parsed = {json.loads(r[0]).get("tid") for r in rows}
        self.assertNotIn(900001, parsed)

    def test_big_import_new_ids_continue(self):
        self.laptop.import_file(self.dest)
        max_part = self.laptop.db.conn.execute(
            "SELECT COALESCE(MAX(id),0) FROM participants").fetchone()[0]
        new_pid = self.laptop.db.add_participant(
            self.tid, "После импорта", 75.0, "Club 1",
            60, "Правая", athlete_id=self.big["db"].conn.execute(
                "SELECT id FROM athletes LIMIT 1").fetchone()[0])
        self.assertGreater(new_pid, max_part)

    def test_big_duplicate_refused_and_unchanged(self):
        self.laptop.import_file(self.dest)
        with self.assertRaises(CompetitionExistsError):
            self.laptop.import_file(self.dest)
        count = self.laptop.db.conn.execute(
            "SELECT COUNT(*) FROM matches").fetchone()[0]
        self.assertEqual(count, self.metadata["counts"]["matches"])

    def test_big_export_stable_after_import(self):
        """Экспорт из ноутбука-2 даёт те же счётчики и данные."""
        self.laptop.import_file(self.dest)
        re_dest = os.path.join(self.laptop.tmp, "big2.armwrestling")
        export_competition(self.laptop.db.conn, self.laptop.state,
                           self.tid, re_dest)
        payload2, md2 = read_archive(re_dest)
        self.assertEqual(md2["counts"], self.metadata["counts"])


class TestStressRoundtripChain(_BigFixture):
    """Цепочка: ноутбук 1 → 2 → 3. Данные не деградируют."""

    def test_three_hop_chain(self):
        self.laptop.import_file(self.dest)
        laptop3 = Laptop2()
        try:
            dest2 = os.path.join(self.laptop.tmp, "hop2.armwrestling")
            export_competition(self.laptop.db.conn, self.laptop.state,
                               self.tid, dest2)
            laptop3.import_file(dest2)
            src_snap = snapshot(self.big["db"], self.tid)
            dst_snap = snapshot(laptop3.db, self.tid)
            assert_snapshot_equal(self, src_snap, dst_snap, self.tid)
            s2 = self.laptop.db.conn.execute(
                "SELECT session_id FROM tournaments WHERE id=?",
                (self.tid,)).fetchone()[0]
            s3 = laptop3.db.conn.execute(
                "SELECT session_id FROM tournaments WHERE id=?",
                (self.tid,)).fetchone()[0]
            s1 = self.big["db"].conn.execute(
                "SELECT session_id FROM tournaments WHERE id=?",
                (self.tid,)).fetchone()[0]
            self.assertTrue(len({s1, s2, s3}) == 3,
                            "каждый импорт создаёт новую сессию")
        finally:
            shutil.rmtree(laptop3.tmp, ignore_errors=True)


class TestStressForceReplace(_BigFixture):
    """Повторное восстановление больших данных: без дублей, рейтинг
    идемпотентен, лишние локальные записи удаляются."""

    def test_force_replace_twice_no_duplicates(self):
        self.laptop.import_file(self.dest)
        self.laptop.import_file(self.dest, force_replace=True)
        self.laptop.import_file(self.dest, force_replace=True)
        count = self.laptop.db.conn.execute(
            "SELECT COUNT(*) FROM matches").fetchone()[0]
        self.assertEqual(count, self.metadata["counts"]["matches"])
        hist = self.laptop.db.conn.execute(
            "SELECT COUNT(*) FROM club_rating_history WHERE tournament_id=?",
            (self.tid,)).fetchone()[0]
        src_hist = self.big["db"].conn.execute(
            "SELECT COUNT(*) FROM club_rating_history WHERE tournament_id=?",
            (self.tid,)).fetchone()[0]
        self.assertEqual(hist, src_hist)

    def test_force_replace_removes_local_extras(self):
        db = self.laptop.db
        self.laptop.import_file(self.dest)
        extra = db.add_participant(self.tid, "Лишний", 70.0, "Club 1",
                                   60, "Правая")
        self.laptop.import_file(self.dest, force_replace=True)
        self.assertIsNone(db.conn.execute(
            "SELECT id FROM participants WHERE id=?",
            (extra,)).fetchone())

    def test_force_replace_rating_sums_consistent(self):
        self.laptop.import_file(self.dest)
        for _ in range(2):
            self.laptop.import_file(self.dest, force_replace=True)
        rows = self.laptop.db.conn.execute(
            "SELECT club_id, rating FROM club_rating").fetchall()
        ratings = dict(rows)
        sums = dict(self.laptop.db.conn.execute(
            "SELECT club_id, SUM(points) FROM club_rating_history "
            "GROUP BY club_id").fetchall())
        for club_id, total in sums.items():
            self.assertEqual(ratings.get(club_id), total)

    def test_force_replace_keeps_pending_ids(self):
        self.laptop.import_file(self.dest)
        ids_before = [r[0] for r in self.laptop.state.conn.execute(
            "SELECT id FROM pending_queue ORDER BY id").fetchall()]
        self.laptop.import_file(self.dest, force_replace=True)
        ids_after = [r[0] for r in self.laptop.state.conn.execute(
            "SELECT id FROM pending_queue ORDER BY id").fetchall()]
        self.assertEqual(ids_before, ids_after)


class TestStressPhotos(unittest.TestCase):
    """Много фотографий: обычный и с паролем."""

    def setUp(self):
        import tempfile
        from tests.export_import import helpers as H
        import armwrestling_tournament as app
        from sync.state import SyncState

        self.tmp = tempfile.mkdtemp(prefix="armw_photos_stress_")
        app.sync_manager = H._NoSync()
        app.DB_PATH = os.path.join(self.tmp, "p.db")
        app.PHOTOS_DIR = os.path.join(self.tmp, "photos")
        os.makedirs(app.PHOTOS_DIR, exist_ok=True)
        db = app.Database()
        state = SyncState(os.path.join(self.tmp, "p_sync.db"))
        tid = db.create_tournament("Photo Cup", "20.08.2026", "Photo City")
        cat = db.add_category(tid, "80 кг", 80, "Правая")
        self.photo_paths = []
        for i in range(60):
            photo = os.path.join(self.tmp, f"foto_{i}.jpg")
            with open(photo, "wb") as f:
                f.write(b"\xff\xd8\xff\xe0" + bytes([i % 256]) * 64)
            self.photo_paths.append(photo)
        self.pids = []
        for i in range(60):
            pid = db.add_participant(tid, f"Участник {i}", 75 + i % 5,
                                     "Club", cat, "Правая",
                                     athlete_id=None)
            db.conn.execute("UPDATE participants SET photo_path=? WHERE id=?",
                            (self.photo_paths[i], pid))
            self.pids.append(pid)
        db.conn.commit()
        self.db, self.state, self.tid = db, state, tid
        self.dest = os.path.join(self.tmp, "photos.armwrestling")
        export_competition(db.conn, state, tid, self.dest,
                           include_photos=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _import_assert(self, dest, password=None):
        laptop = Laptop2()
        try:
            import_competition(laptop.db.conn, laptop.state, dest,
                               password=password,
                               photos_dir=os.path.join(self.tmp, "dst"))
            for i, pid in enumerate(self.pids):
                row = laptop.db.conn.execute(
                    "SELECT photo_path FROM participants WHERE id=?",
                    (pid,)).fetchone()
                self.assertTrue(row["photo_path"], f"фото {i} пропало")
                with open(row["photo_path"], "rb") as f:
                    body = f.read()
                self.assertEqual(body[:4], b"\xff\xd8\xff\xe0")
        finally:
            shutil.rmtree(laptop.tmp, ignore_errors=True)

    def test_many_photos(self):
        self._import_assert(self.dest)

    def test_many_photos_with_password(self):
        import secrets
        pwd = "пароль-стресс-" + secrets.token_hex(4)
        dest = os.path.join(self.tmp, "photos_pwd.armwrestling")
        export_competition(self.db.conn, self.state, self.tid, dest,
                           include_photos=True, password=pwd)
        self._import_assert(dest, password=pwd)

    def test_many_photos_checksum_still_detects_change(self):
        bad = os.path.join(self.tmp, "photos_bad.armwrestling")
        with zipfile.ZipFile(self.dest) as z:
            names = z.namelist()
            contents = {n: z.read(n) for n in names}
        contents["participants.json"] = contents["participants.json"].replace(
            "Участник".encode("utf-8"), "Участник!".encode("utf-8"))
        with zipfile.ZipFile(bad, "w") as z:
            for n in contents:
                z.writestr(n, contents[n])
        laptop = Laptop2()
        try:
            with self.assertRaises(BackupFormatError):
                laptop.import_file(bad)
            count = laptop.db.conn.execute(
                "SELECT COUNT(*) FROM tournaments").fetchone()[0]
            self.assertEqual(count, 0)
        finally:
            shutil.rmtree(laptop.tmp, ignore_errors=True)


class TestStressDamagePositions(unittest.TestCase):
    """Порча большого файла в разных местах — всегда чистый отказ."""

    participants = 300
    pending_ops = 500
    extra_foreign_ops = 100

    def setUp(self):
        self.big = make_big_scenario(participants=self.participants,
                                     pending_ops=self.pending_ops,
                                     extra_foreign_ops=self.extra_foreign_ops)
        self.dest = os.path.join(self.big["tmp"], "big.armwrestling")
        export_competition(self.big["db"].conn, self.big["state"],
                           self.big["tid"], self.dest)
        with open(self.dest, "rb") as f:
            self.data = f.read()
        self.rng = random.Random(42)

    def tearDown(self):
        shutil.rmtree(self.big["tmp"], ignore_errors=True)

    def _corrupt_and_import(self, start, length):
        data = bytearray(self.data)
        for i in range(start, min(start + length, len(data))):
            data[i] = self.rng.randrange(256)
        bad = os.path.join(self.big["tmp"], "damaged.armwrestling")
        with open(bad, "wb") as f:
            f.write(bytes(data))
        laptop = Laptop2()
        try:
            try:
                laptop.import_file(bad)
                outcome = "ok"
            except (BackupFormatError, ImportValidationError,
                    CompetitionExistsError) as e:
                outcome = type(e).__name__
            except Exception as e:
                raise AssertionError(f"неожиданное исключение: {e!r}")
            count = laptop.db.conn.execute(
                "SELECT COUNT(*) FROM tournaments").fetchone()[0]
            if outcome == "ok":
                self.assertEqual(count, 1, "прошло — значит турнир целый")
            else:
                self.assertEqual(count, 0,
                                 f"{outcome}: не должно быть частичных данных")
        finally:
            shutil.rmtree(laptop.tmp, ignore_errors=True)

    def test_damage_at_header(self):
        self._corrupt_and_import(0, 64)

    def test_damage_at_metadata(self):
        self._corrupt_and_import(100, 256)

    def test_damage_in_middle(self):
        self._corrupt_and_import(len(self.data) // 2, 512)

    def test_damage_at_tail(self):
        self._corrupt_and_import(max(0, len(self.data) - 512), 512)

    def test_damage_covering_all(self):
        self._corrupt_and_import(0, len(self.data))


class TestStressIntegrityGuard(unittest.TestCase):
    """Целостность больших данных: повреждение на уровне БД блокирует
    обычный экспорт (но НЕ аварийный)."""

    def setUp(self):
        self.big = make_big_scenario(participants=200, pending_ops=100)
        self.tid = self.big["tid"]

    def tearDown(self):
        shutil.rmtree(self.big["tmp"], ignore_errors=True)

    def test_damaged_db_blocks_export_but_emergency_works(self):
        db = self.big["db"]
        db.conn.execute("UPDATE matches SET winner_id=999999 "
                        "WHERE id=?", (self.big["matches"][0],))
        db.conn.commit()
        problems = validate_competition_integrity(db.conn, self.tid)
        self.assertTrue(problems)
        dest = os.path.join(self.big["tmp"], "normal.armwrestling")
        with self.assertRaises(ExportError):
            export_competition(db.conn, self.big["state"], self.tid, dest)
        emergency = os.path.join(self.big["tmp"], "emergency.armwrestling")
        export_competition(db.conn, self.big["state"], self.tid, emergency,
                           emergency=True)
        self.assertTrue(os.path.exists(emergency))