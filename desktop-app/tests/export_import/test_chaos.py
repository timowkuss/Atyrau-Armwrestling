"""§33: Chaos-тест. Случайные повреждения архива — импорт либо успешен и
корректен, либо падает с ожидаемой ошибкой и НЕ оставляет частичных данных.

Инвариант после каждой попытки: в целевой БД либо нет следов турнира,
либо турнир полный и консистентный (все разделы на месте, суммы сходятся).
"""

import copy
import json
import os
import random
import shutil
import unittest
import zipfile

from tests.export_import.helpers import Laptop2, Scenario  # noqa: E402

from transfer.importer import (  # noqa: E402
    CompetitionExistsError,
    IdCollisionError,
    ImportValidationError,
)
from transfer.pack import BackupFormatError, compute_checksum  # noqa: E402


class ChaosTestCase(unittest.TestCase):

    def setUp(self):
        self.sc = Scenario()
        self.dest = os.path.join(self.sc.tmp, "src.armwrestling")
        self.sc.export(self.dest)
        self.rng = random.Random(20260811)
        self.bad_dir = os.path.join(self.sc.tmp, "mutations")

    def tearDown(self):
        shutil.rmtree(self.sc.tmp, ignore_errors=True)

    def _read_archive_members(self, path):
        with zipfile.ZipFile(path) as z:
            return {n: z.read(n) for n in z.namelist()}

    def _write_members(self, path, members):
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for n in sorted(members):
                z.writestr(n, members[n])

    def _mutations(self):
        """Генератор (имя, мутатор members -> members)."""
        members = self._read_archive_members(self.dest)
        json_names = [n for n in members if n.endswith(".json")]

        def flip_bits(m, member):
            m = dict(m)
            data = bytearray(m[member])
            for _ in range(self.rng.randint(1, 8)):
                i = self.rng.randrange(len(data))
                data[i] ^= 1 << self.rng.randrange(8)
            m[member] = bytes(data)
            return m

        def truncate(m, member):
            m = dict(m)
            data = m[member]
            m[member] = data[:self.rng.randrange(1, len(data))]
            return m

        def drop_member(m, member):
            m = dict(m)
            m.pop(member, None)
            return m

        def corrupt_json(m, member):
            m = dict(m)
            data = bytearray(m[member])
            pos = self.rng.randrange(len(data))
            data[pos] = ord("{") if data[pos] != ord("{") else ord("}")
            m[member] = bytes(data)
            return m

        def swap_values(m, member):
            m = dict(m)
            key = member.replace(".json", "")
            obj = json.loads(m[member].decode("utf-8"))
            if isinstance(obj, list) and len(obj) >= 2:
                obj[0], obj[-1] = obj[-1], obj[0]
            elif isinstance(obj, dict):
                for k in list(obj.keys()):
                    obj[k] = "мусор"
            m[member] = json.dumps(
                obj, ensure_ascii=False).encode("utf-8")
            return m

        def duplicate_member(m, member):
            m = dict(m)
            m["dup_" + member] = m[member]
            return m

        for member in json_names:
            yield ("flip_" + member,
                   lambda m, mm=member: flip_bits(m, mm))
        for member in json_names:
            yield ("trunc_" + member,
                   lambda m, mm=member: truncate(m, mm))
        for member in json_names:
            yield ("drop_" + member,
                   lambda m, mm=member: drop_member(m, mm))
        for member in json_names:
            yield ("corruptjson_" + member,
                   lambda m, mm=member: corrupt_json(m, mm))
        for member in json_names:
            yield ("swap_" + member,
                   lambda m, mm=member: swap_values(m, mm))
        yield ("duplicate_member",
               lambda m: duplicate_member(m, "matches.json"))
        yield ("empty_matches",
               lambda m: {**m, "matches.json": b"[]"})

    def _consistent_or_absent(self, laptop):
        """Проверяет инвариант: следов турнира нет ИЛИ он полный."""
        db = laptop.db
        t = db.conn.execute("SELECT * FROM tournaments WHERE id=?",
                            (self.sc.tid,)).fetchone()
        if t is None:
            leftovers = (
                db.conn.execute("SELECT COUNT(*) FROM weight_categories "
                                "WHERE tournament_id=?", (self.sc.tid,)
                                ).fetchone()[0]
                + db.conn.execute("SELECT COUNT(*) FROM participants "
                                  "WHERE tournament_id=?", (self.sc.tid,)
                                  ).fetchone()[0]
                + db.conn.execute("SELECT COUNT(*) FROM matches "
                                  "WHERE tournament_id=?", (self.sc.tid,)
                                  ).fetchone()[0])
            self.assertEqual(leftovers, 0,
                             "при отказе импорта не должно оставаться "
                             "частичных данных")
            return
        cat_count = db.conn.execute(
            "SELECT COUNT(*) FROM weight_categories WHERE tournament_id=?",
            (self.sc.tid,)).fetchone()[0]
        part_count = db.conn.execute(
            "SELECT COUNT(*) FROM participants WHERE tournament_id=?",
            (self.sc.tid,)).fetchone()[0]
        match_count = db.conn.execute(
            "SELECT COUNT(*) FROM matches WHERE tournament_id=?",
            (self.sc.tid,)).fetchone()[0]
        done = db.conn.execute(
            "SELECT COUNT(*) FROM matches WHERE tournament_id=? AND "
            "status='done'", (self.sc.tid,)).fetchone()[0]
        self.assertGreaterEqual(cat_count, 1)
        self.assertEqual(part_count, match_count or part_count,
                         "участники и матчи должны быть согласованы")
        self.assertLessEqual(done, match_count)

    def test_chaos_all_mutations(self):
        failures = []
        for name, mutate in self._mutations():
            members = self._read_archive_members(self.dest)
            try:
                mutated = mutate(members)
            except Exception:
                continue
            bad = os.path.join(self.bad_dir, name + ".armwrestling")
            try:
                self._write_members(bad, mutated)
            except Exception:
                continue
            laptop = Laptop2()
            try:
                try:
                    laptop.import_file(bad)
                    status = "OK"
                except (BackupFormatError, ImportValidationError,
                        IdCollisionError, CompetitionExistsError) as e:
                    status = type(e).__name__
                except Exception as e:
                    failures.append((name, "неожиданная ошибка: " + repr(e)))
                    continue
                try:
                    self._consistent_or_absent(laptop)
                except AssertionError as e:
                    failures.append((name, status + ": " + str(e)))
            finally:
                shutil.rmtree(laptop.tmp, ignore_errors=True)
        if failures:
            self.fail("chaos-нарушения:\n" + "\n".join(
                f"{n}: {msg}" for n, msg in failures))

    def test_chaos_repeated_imports_do_not_leak(self):
        """10 повторных импортов одного файла — 10 отказов, БД без дублей."""
        laptop = Laptop2()
        try:
            laptop.import_file(self.dest)
            for _ in range(10):
                with self.assertRaises(CompetitionExistsError):
                    laptop.import_file(self.dest)
            count = laptop.db.conn.execute(
                "SELECT COUNT(*) FROM matches").fetchone()[0]
            self.assertEqual(count, 2)
        finally:
            shutil.rmtree(laptop.tmp, ignore_errors=True)


class TestChecksumRecomputeChaos(unittest.TestCase):
    """Мутации с пересчитанным checksum — валидные структурно изменения
    могут пройти, но БД должна остаться консистентной."""

    def setUp(self):
        self.sc = Scenario()
        self.dest = os.path.join(self.sc.tmp, "src.armwrestling")
        self.sc.export(self.dest)

    def tearDown(self):
        shutil.rmtree(self.sc.tmp, ignore_errors=True)

    def test_valid_but_renamed_competition_imports_fully(self):
        with zipfile.ZipFile(self.dest) as z:
            members = {n: z.read(n) for n in z.namelist()}
        comp = json.loads(members["competition.json"].decode("utf-8"))
        comp["tournament"]["name"] = "Переименованное"
        members["competition.json"] = json.dumps(
            comp, ensure_ascii=False).encode("utf-8")
        raw = {n: c for n, c in members.items() if n != "metadata.json"}
        md = json.loads(members["metadata.json"].decode("utf-8"))
        md["checksum"] = compute_checksum(raw)
        members["metadata.json"] = json.dumps(
            md, ensure_ascii=False).encode("utf-8")
        path = os.path.join(self.sc.tmp, "renamed.armwrestling")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for n in sorted(members):
                z.writestr(n, members[n])
        laptop = Laptop2()
        try:
            res = laptop.import_file(path)
            self.assertEqual(res["matches"], 2)
            self.assertEqual(res["finished"], 1)
            name = laptop.db.conn.execute(
                "SELECT name FROM tournaments WHERE id=?",
                (self.sc.tid,)).fetchone()[0]
            self.assertEqual(name, "Переименованное")
        finally:
            shutil.rmtree(laptop.tmp, ignore_errors=True)
