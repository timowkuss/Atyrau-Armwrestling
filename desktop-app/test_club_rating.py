import os
import sqlite3
import tempfile
import unittest

import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from club_rating import (  # noqa: E402
    REASON_ATHLETE_REMOVED,
    REASON_FIRST_PARTICIPATION,
    REASON_INACTIVITY,
    REASON_PLACE,
    add_months,
    add_points,
    apply_athlete_removed,
    check_inactive_athletes,
    finalize_competition,
    get_club_rating,
    get_club_rating_history,
    recalc_club_rating_from_history,
)


def make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE tournaments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, date TEXT NOT NULL, location TEXT,
        bracket_system TEXT DEFAULT 'double', format_type TEXT DEFAULT 'separate',
        status TEXT DEFAULT 'active', finished_at TEXT
    );
    CREATE TABLE weight_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT, tournament_id INTEGER NOT NULL,
        name TEXT NOT NULL, max_weight REAL, hand TEXT DEFAULT 'Обе', is_plus INTEGER DEFAULT 0
    );
    CREATE TABLE participants (
        id INTEGER PRIMARY KEY AUTOINCREMENT, tournament_id INTEGER NOT NULL,
        name TEXT NOT NULL, weight REAL, club TEXT, category_id INTEGER,
        hand TEXT DEFAULT 'Обе', photo_path TEXT, athlete_id INTEGER
    );
    CREATE TABLE matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT, tournament_id INTEGER NOT NULL,
        category_id INTEGER NOT NULL, hand TEXT, round_name TEXT, bracket TEXT DEFAULT 'winners',
        match_order INTEGER DEFAULT 0, p1_id INTEGER, p2_id INTEGER, winner_id INTEGER,
        p1_losses INTEGER DEFAULT 0, p2_losses INTEGER DEFAULT 0, is_bye INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending', win_next_id INTEGER, win_next_slot INTEGER DEFAULT 1,
        lose_next_id INTEGER, lose_next_slot INTEGER DEFAULT 1, stage INTEGER DEFAULT 0
    );
    CREATE TABLE athletes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, first_name TEXT NOT NULL, last_name TEXT NOT NULL,
        birth_date TEXT NOT NULL, gender TEXT NOT NULL, club TEXT, club_id INTEGER,
        rank TEXT, photo_path TEXT, iin TEXT, phone TEXT, coach_id INTEGER,
        club_active INTEGER DEFAULT 0, last_competition_date TEXT, next_inactive_date TEXT,
        join_club_date TEXT, created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE clubs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, city TEXT,
        address TEXT, founded_year INTEGER, logo_path TEXT, created_at TEXT
    );
    CREATE TABLE club_rating (
        id INTEGER PRIMARY KEY AUTOINCREMENT, club_id INTEGER NOT NULL UNIQUE,
        rating INTEGER NOT NULL DEFAULT 0, updated_at TEXT
    );
    CREATE TABLE club_rating_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, club_id INTEGER NOT NULL,
        athlete_id INTEGER, tournament_id INTEGER, points INTEGER NOT NULL,
        reason TEXT NOT NULL, description TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE UNIQUE INDEX uq_club_rating_history
        ON club_rating_history (club_id, athlete_id, tournament_id, reason, description);
    """)
    return conn


def add_athlete(conn, last, club_id=None, active=0):
    cur = conn.execute(
        "INSERT INTO athletes (first_name, last_name, birth_date, gender, club_id, club_active) "
        "VALUES ('', ?, '01.01.2000', 'M', ?, ?)",
        (last, club_id, active),
    )
    return cur.lastrowid


def add_participant(conn, tid, cat_id, name, athlete_id, club_name=""):
    cur = conn.execute(
        "INSERT INTO participants (tournament_id, name, weight, club, category_id, athlete_id) "
        "VALUES (?, ?, 70, ?, ?, ?)",
        (tid, name, club_name, cat_id, athlete_id),
    )
    return cur.lastrowid


def add_match(conn, tid, cat_id, hand, p1, p2, winner, stage, bracket="winners"):
    conn.execute(
        "INSERT INTO matches (tournament_id, category_id, hand, p1_id, p2_id, winner_id, "
        "status, win_next_id, stage, bracket) VALUES (?,?,?,?,?,?,'done',?,?,?)",
        (tid, cat_id, hand, p1, p2, winner, None, stage, bracket),
    )


class ClubRatingTest(unittest.TestCase):
    def test_new_club_starts_at_zero(self):
        conn = make_db()
        self.assertEqual(get_club_rating(conn, 1), 0)

    def test_add_points_and_clamp_negative(self):
        conn = make_db()
        conn.execute("INSERT INTO clubs (id, name) VALUES (1, 'Алга')")
        r = add_points(conn, 1, None, None, -50, REASON_ATHLETE_REMOVED, "x")
        self.assertTrue(r["applied"])
        self.assertEqual(r["rating"], 0)
        self.assertEqual(get_club_rating(conn, 1), 0)
        hist = get_club_rating_history(conn, 1)
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["points"], -50)

    def test_add_points_idempotent(self):
        conn = make_db()
        conn.execute("INSERT INTO clubs (id, name) VALUES (1, 'Алга')")
        add_points(conn, 1, None, None, 10, REASON_PLACE, "desc")
        r2 = add_points(conn, 1, None, None, 10, REASON_PLACE, "desc")
        self.assertFalse(r2["applied"])
        self.assertEqual(get_club_rating(conn, 1), 10)
        self.assertEqual(len(get_club_rating_history(conn, 1)), 1)

    def test_removal_penalty(self):
        conn = make_db()
        conn.execute("INSERT INTO clubs (id, name) VALUES (1, 'Алга')")
        aid = add_athlete(conn, "Иванов", club_id=1)
        apply_athlete_removed(conn, aid, 1)
        self.assertEqual(get_club_rating(conn, 1), 0)
        hist = get_club_rating_history(conn, 1)
        self.assertEqual(hist[0]["reason"], REASON_ATHLETE_REMOVED)
        self.assertEqual(hist[0]["points"], -10)

    def test_inactivity_penalty_once(self):
        conn = make_db()
        conn.execute("INSERT INTO clubs (id, name) VALUES (1, 'Алга')")
        aid = add_athlete(conn, "Иванов", club_id=1, active=1)
        conn.execute(
            "UPDATE athletes SET next_inactive_date='2000-01-01' WHERE id=?", (aid,)
        )
        n = check_inactive_athletes(conn, today=__import__("datetime").date(2001, 1, 1))
        self.assertEqual(n, 1)
        hist = get_club_rating_history(conn, 1)
        self.assertEqual(hist[0]["reason"], REASON_INACTIVITY)
        self.assertEqual(hist[0]["points"], -5)
        n2 = check_inactive_athletes(conn, today=__import__("datetime").date(2002, 1, 1))
        self.assertEqual(n2, 0)
        self.assertEqual(len(get_club_rating_history(conn, 1)), 1)

    def test_active_athlete_no_penalty(self):
        conn = make_db()
        conn.execute("INSERT INTO clubs (id, name) VALUES (1, 'Алга')")
        aid = add_athlete(conn, "Иванов", club_id=1, active=1)
        conn.execute(
            "UPDATE athletes SET next_inactive_date='2030-01-01' WHERE id=?", (aid,)
        )
        n = check_inactive_athletes(conn)
        self.assertEqual(n, 0)

    def test_first_participation_gives_plus5(self):
        conn = make_db()
        conn.execute("INSERT INTO clubs (id, name) VALUES (1, 'Алга')")
        aid = add_athlete(conn, "Иванов", club_id=1, active=0)
        tid = conn.execute(
            "INSERT INTO tournaments (name, date, status) VALUES ('Т', '2024-01-01', 'finished')"
        ).lastrowid
        cat_id = conn.execute(
            "INSERT INTO weight_categories (tournament_id, name, hand) VALUES (?, 'до 70', 'Правая')",
            (tid,),
        ).lastrowid
        pid = add_participant(conn, tid, cat_id, "Иванов", aid, "Алга")
        p2 = add_participant(conn, tid, cat_id, "Петров", None)
        add_match(conn, tid, cat_id, "Правая", pid, p2, pid, 1, "final")
        res = finalize_competition(conn, tid)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(get_club_rating(conn, 1), 15)  # 5 участие + 10 первое место
        a = conn.execute("SELECT * FROM athletes WHERE id=?", (aid,)).fetchone()
        self.assertEqual(a["club_active"], 1)
        self.assertEqual(a["last_competition_date"], "2024-01-01")
        self.assertEqual(a["next_inactive_date"], "2024-07-01")

    def test_repeat_participation_no_extra(self):
        conn = make_db()
        conn.execute("INSERT INTO clubs (id, name) VALUES (1, 'Алга')")
        aid = add_athlete(conn, "Иванов", club_id=1, active=1)
        tid = conn.execute(
            "INSERT INTO tournaments (name, date, status) VALUES ('Т', '2024-01-01', 'finished')"
        ).lastrowid
        cat_id = conn.execute(
            "INSERT INTO weight_categories (tournament_id, name, hand) VALUES (?, 'до 70', 'Правая')",
            (tid,),
        ).lastrowid
        pid = add_participant(conn, tid, cat_id, "Иванов", aid, "Алга")
        finalize_competition(conn, tid)
        self.assertEqual(get_club_rating(conn, 1), 0)  # активен -> нет +5 и нет матчей
        self.assertEqual(len(get_club_rating_history(conn, 1)), 0)

    def test_place_points_bracket(self):
        conn = make_db()
        conn.execute("INSERT INTO clubs (id, name) VALUES (1, 'Алга')")
        conn.execute("INSERT INTO clubs (id, name) VALUES (2, 'Спартак')")
        a1 = add_athlete(conn, "Иванов", club_id=1, active=1)
        a2 = add_athlete(conn, "Петров", club_id=2, active=1)
        tid = conn.execute(
            "INSERT INTO tournaments (name, date, status) VALUES ('Т', '2024-01-01', 'finished')"
        ).lastrowid
        cat_id = conn.execute(
            "INSERT INTO weight_categories (tournament_id, name, hand) VALUES (?, 'до 70', 'Правая')",
            (tid,),
        ).lastrowid
        p1 = add_participant(conn, tid, cat_id, "Иванов", a1, "Алга")
        p2 = add_participant(conn, tid, cat_id, "Петров", a2, "Спартак")
        add_match(conn, tid, cat_id, "Правая", p1, p2, p1, 1, "final")
        finalize_competition(conn, tid)
        self.assertEqual(get_club_rating(conn, 1), 10)  # 1 место
        self.assertEqual(get_club_rating(conn, 2), 6)   # 2 место
        self.assertEqual(len(get_club_rating_history(conn, 1)), 1)
        self.assertEqual(get_club_rating_history(conn, 1)[0]["reason"], REASON_PLACE)

    def test_top3_only(self):
        conn = make_db()
        conn.execute("INSERT INTO clubs (id, name) VALUES (1, 'Алга')")
        conn.execute("INSERT INTO clubs (id, name) VALUES (2, 'Спартак')")
        conn.execute("INSERT INTO clubs (id, name) VALUES (3, 'Каспий')")
        conn.execute("INSERT INTO clubs (id, name) VALUES (4, 'Волна')")
        aids = []
        pids = []
        tid = conn.execute(
            "INSERT INTO tournaments (name, date, status) VALUES ('Т', '2024-01-01', 'finished')"
        ).lastrowid
        cat_id = conn.execute(
            "INSERT INTO weight_categories (tournament_id, name, hand) VALUES (?, 'до 70', 'Правая')",
            (tid,),
        ).lastrowid
        for i, club_id in enumerate([1, 2, 3, 4], start=1):
            aid = add_athlete(conn, f"С{i}", club_id=club_id, active=1)
            aids.append(aid)
            pids.append(add_participant(conn, tid, cat_id, f"С{i}", aid))
        # Полуфиналы + финал (без losers): С1 чемпион, С3 2 место, С2 3 место.
        add_match(conn, tid, cat_id, "Правая", pids[0], pids[1], pids[0], 1, "winners")
        add_match(conn, tid, cat_id, "Правая", pids[2], pids[3], pids[2], 1, "winners")
        add_match(conn, tid, cat_id, "Правая", pids[0], pids[2], pids[0], 2, "final")
        finalize_competition(conn, tid)
        self.assertEqual(get_club_rating(conn, 1), 10)  # С1 — чемпион
        self.assertEqual(get_club_rating(conn, 3), 6)   # С3 — 2 место
        self.assertEqual(get_club_rating(conn, 2), 3)   # С2 — 3 место
        self.assertEqual(get_club_rating(conn, 4), 0)

    def test_athlete_without_club_no_points(self):
        conn = make_db()
        aid = add_athlete(conn, "Иванов", club_id=None, active=0)
        tid = conn.execute(
            "INSERT INTO tournaments (name, date, status) VALUES ('Т', '2024-01-01', 'finished')"
        ).lastrowid
        cat_id = conn.execute(
            "INSERT INTO weight_categories (tournament_id, name, hand) VALUES (?, 'до 70', 'Правая')",
            (tid,),
        ).lastrowid
        add_participant(conn, tid, cat_id, "Иванов", aid)
        finalize_competition(conn, tid)
        self.assertEqual(get_club_rating(conn, 999), 0)

    def test_finalize_skips_unfinished(self):
        conn = make_db()
        tid = conn.execute(
            "INSERT INTO tournaments (name, date, status) VALUES ('Т', '2024-01-01', 'active')"
        ).lastrowid
        res = finalize_competition(conn, tid)
        self.assertEqual(res["status"], "skipped")

    def test_add_months(self):
        self.assertEqual(add_months(__import__("datetime").date(2024, 1, 31), 1),
                         __import__("datetime").date(2024, 2, 29))
        self.assertEqual(add_months(__import__("datetime").date(2023, 12, 15), 6),
                         __import__("datetime").date(2024, 6, 15))

    def test_recalc_from_history(self):
        conn = make_db()
        conn.execute("INSERT INTO clubs (id, name) VALUES (1, 'Алга')")
        aid = add_athlete(conn, "Иванов", club_id=1)
        add_points(conn, 1, aid, None, 10, REASON_PLACE, "1 место")
        add_points(conn, 1, aid, None, -10, REASON_ATHLETE_REMOVED, "удалён")
        self.assertEqual(recalc_club_rating_from_history(conn, 1), 0)
        add_points(conn, 1, aid, None, 5, REASON_FIRST_PARTICIPATION, "возврат")
        self.assertEqual(recalc_club_rating_from_history(conn, 1), 5)

    def test_dvoeborie_standings(self):
        conn = make_db()
        conn.execute("INSERT INTO clubs (id, name) VALUES (1, 'Алга')")
        conn.execute("INSERT INTO clubs (id, name) VALUES (2, 'Спартак')")
        a1 = add_athlete(conn, "Иванов", club_id=1, active=1)
        a2 = add_athlete(conn, "Петров", club_id=2, active=1)
        tid = conn.execute(
            "INSERT INTO tournaments (name, date, status, format_type) "
            "VALUES ('Т', '2024-01-01', 'finished', 'dvoeborie')"
        ).lastrowid
        cat_id = conn.execute(
            "INSERT INTO weight_categories (tournament_id, name, hand) VALUES (?, 'до 70', 'Обе')",
            (tid,),
        ).lastrowid
        p1 = add_participant(conn, tid, cat_id, "Иванов", a1, "Алга")
        p2 = add_participant(conn, tid, cat_id, "Петров", a2, "Спартак")
        # Правая: Иванов 1 место, Петров 2 место.
        add_match(conn, tid, cat_id, "Правая", p1, p2, p1, 1, "final")
        # Левая: Иванов 1 место, Петров 2 место.
        add_match(conn, tid, cat_id, "Левая", p1, p2, p1, 1, "final")
        finalize_competition(conn, tid)
        self.assertEqual(get_club_rating(conn, 1), 10)  # Иванов 1 место по двоеборью
        self.assertEqual(get_club_rating(conn, 2), 6)   # Петров 2 место по двоеборью


if __name__ == "__main__":
    unittest.main(verbosity=2)
