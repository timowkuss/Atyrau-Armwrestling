"""
╔════╗
║        АРМРЕСТЛИНГ — МЕНЕДЖЕР СОРЕВНОВАНИЙ               ║
║        Формат: до 2 поражений (Double Elimination)       ║
║        + Бейджики с штрихкодами + Сканер                 ║
║        Технологии: Python + CustomTkinter + SQLite       ║
╚════╝

Установка зависимостей:
    pip install customtkinter pillow reportlab

Запуск:
    python armwrestling_tournament.py
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import sqlite3
import os
import sys
import math
import json
from datetime import datetime
from pathlib import Path
import random
from collections import OrderedDict
from flask import Flask
from threading import Thread
import webbrowser

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageOps
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.graphics.barcode.code128 import Code128
    REPORTLAB_AVAILABLE = True
    _FONT_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    try:
        pdfmetrics.registerFont(TTFont("Arial", str(_FONT_DIR / "arial.ttf")))
        pdfmetrics.registerFont(TTFont("Arial-Bold", str(_FONT_DIR / "arialbd.ttf")))
    except Exception:
        pass
except ImportError:
    REPORTLAB_AVAILABLE = False

# ─── Тема приложения ────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DB_PATH = Path(__file__).resolve().parent / "armwrestling.db"
PHOTOS_DIR = Path("photos")
PHOTOS_DIR.mkdir(exist_ok=True)

# ─── Штрихкод ────
BARCODE_PREFIX = "ARM"
DELETE_ATHLETE_PASSWORD = "1234"  # смените на свой пароль


def get_barcode_value(participant_id):
    """Генерирует уникальное значение штрихкода для участника."""
    return f"{BARCODE_PREFIX}{participant_id:06d}"

def parse_barcode_value(barcode_str):
    """Извлекает ID участника из значения штрихкода."""
    barcode_str = barcode_str.strip()
    if barcode_str.startswith(BARCODE_PREFIX):
        try:
            return int(barcode_str[len(BARCODE_PREFIX):])
        except ValueError:
            return None
    return None

from collections import OrderedDict

from collections import OrderedDict

AGE_CATEGORY_RULES = OrderedDict([
    ("Sub-Junior Girls", {"gender": "F", "level": 0, "max_age": 15,
        "weights": [40, 45, 50, 55, 60, 70, "70+"]}),
    ("Sub-Junior Boys",  {"gender": "M", "level": 0, "max_age": 15,
        "weights": [36, 40, 45, 50, 55, 60, 65, 70, "80+"]}),
    ("Junior Girls",     {"gender": "F", "level": 1, "max_age": 18,
        "weights": [45, 50, 55, 60, 65, 70, "70+"]}),
    ("Junior Boys",      {"gender": "M", "level": 1, "max_age": 18,
        "weights": [50, 55, 60, 65, 70, 75, 80, 90, "90+"]}),
    ("Youth Women",      {"gender": "F", "level": 2, "max_age": 23,
        "weights": [50, 55, 60, 65, 70, 80, "90+"]}),
    ("Youth Men",        {"gender": "M", "level": 2, "max_age": 23,
        "weights": [55, 60, 65, 70, 75, 80, 85, 90, 100, 110, "110+"]}),
    ("Senior Women",     {"gender": "F", "level": 3, "max_age": None,
        "weights": [50, 55, 60, 65, 70, 80, 90, "90+"]}),
    ("Senior Men",       {"gender": "M", "level": 3, "max_age": None,
        "weights": [55, 60, 65, 70, 75, 80, 85, 90, 100, 110, "110+"]}),
    ("Absolute Women",   {"gender": "F", "level": 99, "max_age": None,
        "weights": ["Absolute"]}),
    ("Absolute Men",     {"gender": "M", "level": 99, "max_age": None,
        "weights": ["Absolute"]}),
])
RANKS = ["КМС", "МС", "МСМК", "ЗМС", "Без звания"]
HAND_SUFFIX = {"Левая": "Left", "Правая": "Right", "Обе": "Both"}

# ─── Очки двоеборья (сумма левой + правой руки) ────
# 1 место - 10, 2 место - 7, 3 место - 5, 4 место - 4,
# 5 место - 3, 6 место - 2, 7 место - 1, 8 место и ниже - 0
DVOEBORIE_POINTS = {1: 10, 2: 7, 3: 5, 4: 4, 5: 3, 6: 2, 7: 1}


def get_dvoeborie_points(place):
    """Очки двоеборья за место, занятое на ОДНОЙ руке."""
    if not place:
        return 0
    return DVOEBORIE_POINTS.get(place, 0)



def compute_age_category(birth_date_str, gender, tournament_year=None):
    """Считает возраст по календарному году (turning age), не по точной дате."""
    if tournament_year is None:
        tournament_year = datetime.now().year
    birth_year = int(birth_date_str.split(".")[-1])   # 'дд.мм.гггг' -> год последним
    turning_age = tournament_year - birth_year

    if turning_age <= 15:
        level = 0
    elif turning_age <= 18:
        level = 1
    elif turning_age <= 23:
        level = 2
    else:
        level = 3

    for name, rule in AGE_CATEGORY_RULES.items():
        if rule["gender"] == gender and rule["level"] == level:
            return name
    return None


def is_eligible_for_category(natural_category, target_category):
    """Может ли спортсмен со своей natural-категорией участвовать в target_category.
    Правило простое: играть можно только вверх (свой уровень или старше),
    Senior — самый старший уровень, поэтому выше него никто не играет,
    а сам Senior никуда, кроме Senior, не спускается."""
    if not natural_category or not target_category:
        return False
    nat = AGE_CATEGORY_RULES[natural_category]
    tgt = AGE_CATEGORY_RULES[target_category]
    if nat["gender"] != tgt["gender"]:
        return False
    return nat["level"] <= tgt["level"]


def suggest_weight_class(actual_weight, weight_list):
    """Ближайший класс >= фактического веса, либо '+'-класс, если тяжелее всех."""
    numeric = sorted(w for w in weight_list if isinstance(w, (int, float)))
    for w in numeric:
        if actual_weight <= w:
            return w
    return next((w for w in weight_list if isinstance(w, str) and w.endswith("+")), None)

# ════
#  БАЗА ДАННЫХ
# ════
class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        # WAL резко ускоряет commit(): вместо полного fsync на каждую запись
        # используется журнал с батчевой записью. NORMAL синхронность в паре
        # с WAL безопасна (не теряет данные при сбое приложения, только при
        # падении ОС) и на порядок быстрее дефолтного FULL.
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._create_tables()

    def _create_tables(self):
        cur = self.conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS tournaments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            weight_tolerance REAL DEFAULT 0,
            name TEXT NOT NULL,
            date TEXT NOT NULL,
            location TEXT,
            bracket_system TEXT DEFAULT 'double',
            format_type TEXT DEFAULT 'separate',
            status TEXT DEFAULT 'active',
            finished_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS weight_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            max_weight REAL,
            hand TEXT DEFAULT 'Обе',
            FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            weight REAL,
            club TEXT,
            category_id INTEGER,
            hand TEXT DEFAULT 'Обе',
            photo_path TEXT,
            FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES weight_categories(id)
        );

        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            hand TEXT DEFAULT 'Правая',
            round_name TEXT,
            bracket TEXT DEFAULT 'winners',
            match_order INTEGER DEFAULT 0,
            p1_id INTEGER,
            p2_id INTEGER,
            winner_id INTEGER,
            p1_losses INTEGER DEFAULT 0,
            p2_losses INTEGER DEFAULT 0,
            is_bye INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            win_next_id INTEGER,
            win_next_slot INTEGER DEFAULT 1,
            lose_next_id INTEGER,
            lose_next_slot INTEGER DEFAULT 1,
            FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES weight_categories(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS athletes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            birth_date TEXT NOT NULL,        -- 'YYYY-MM-DD'
            gender TEXT NOT NULL CHECK (gender IN ('M','F')),
            club TEXT,
            rank TEXT,                       -- звание
            photo_path TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
                          
        CREATE TABLE IF NOT EXISTS dvoeborie_overrides (
            tournament_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            pid INTEGER NOT NULL,
            manual_rank INTEGER NOT NULL,
            PRIMARY KEY (tournament_id, category_id, pid)
        );
        """)

        wc_cols = [r[1] for r in self.conn.execute("PRAGMA table_info(weight_categories)").fetchall()]
        for col, ddl in [("age_category", "TEXT"), ("gender", "TEXT"), ("is_plus", "INTEGER DEFAULT 0")]:
            if col not in wc_cols:
                self.conn.execute(f"ALTER TABLE weight_categories ADD COLUMN {col} {ddl}")
        
        t_cols = [r[1] for r in self.conn.execute("PRAGMA table_info(tournaments)").fetchall()]
        if "weight_tolerance" not in t_cols:
            self.conn.execute("ALTER TABLE tournaments ADD COLUMN weight_tolerance REAL DEFAULT 0")
        if "bracket_system" not in t_cols:
            self.conn.execute("ALTER TABLE tournaments ADD COLUMN bracket_system TEXT DEFAULT 'double'")
        if "format_type" not in t_cols:
            self.conn.execute("ALTER TABLE tournaments ADD COLUMN format_type TEXT DEFAULT 'separate'")
        if "status" not in t_cols:
            self.conn.execute("ALTER TABLE tournaments ADD COLUMN status TEXT DEFAULT 'active'")
        if "finished_at" not in t_cols:
            self.conn.execute("ALTER TABLE tournaments ADD COLUMN finished_at TEXT")

        self.conn.commit()
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(matches)").fetchall()]
        for col, defval in [("win_next_id", "NULL"), ("win_next_slot", "1"),
                    ("lose_next_id", "NULL"), ("lose_next_slot", "1"),
                    ("stage", "0"),
                    # Номер стола/трансляция на табло сайта — раньше жил только
                    # как временный атрибут открытого окна сетки (self.table_number)
                    # и назначался автоматически (1 или 2) по числу открытых окон.
                    # Теперь это осознанный выбор организатора в самом окне сетки,
                    # и он должен переживать закрытие/переоткрытие окна — поэтому
                    # храним его локально так же, как на сервере.
                    ("table_number", "NULL")]:
            if col not in cols:
                self.conn.execute(f"ALTER TABLE matches ADD COLUMN {col} INTEGER DEFAULT {defval}")
        p_cols = [r[1] for r in self.conn.execute("PRAGMA table_info(participants)").fetchall()]
        if "age_category" not in p_cols:
            self.conn.execute("ALTER TABLE participants ADD COLUMN age_category TEXT DEFAULT 'Senior'")
        self.conn.commit()
    
        if "athlete_id" not in p_cols:
            self.conn.execute("ALTER TABLE participants ADD COLUMN athlete_id INTEGER REFERENCES athletes(id)")

    def create_tournament(self, name, date, location="", weight_tolerance=0,
                          bracket_system="double", format_type="separate"):
        cur = self.conn.execute(
            "INSERT INTO tournaments (name, date, location, weight_tolerance, "
            "bracket_system, format_type) VALUES (?,?,?,?,?,?)",
            (name, date, location, weight_tolerance, bracket_system, format_type))
        self.conn.commit()
        return cur.lastrowid

    def get_tournaments(self):
        return self.conn.execute("SELECT * FROM tournaments ORDER BY date DESC").fetchall()

    def get_tournament(self, tid):
        return self.conn.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()

    def delete_tournament(self, tid):
        self.conn.execute("DELETE FROM tournaments WHERE id=?", (tid,))
        self.conn.commit()

    def finish_tournament(self, tid):
        """Помечает турнир завершённым: редактирование (участники, категории,
        сетки) блокируется в UI, но результаты и составы сохраняются как
        исторический архив. Если позже удалить спортсмена из общего реестра,
        его записи участия в завершённых турнирах НЕ удаляются."""
        self.conn.execute(
            "UPDATE tournaments SET status='finished', finished_at=datetime('now') WHERE id=?",
            (tid,))
        self.conn.commit()

    def reopen_tournament(self, tid):
        """Возвращает турнир в активное состояние (снова доступно редактирование)."""
        self.conn.execute(
            "UPDATE tournaments SET status='active', finished_at=NULL WHERE id=?", (tid,))
        self.conn.commit()

    def is_tournament_finished(self, tid):
        t = self.get_tournament(tid)
        return bool(t and "status" in t.keys() and t["status"] == "finished")

    def add_category(self, tid, name, max_weight, hand="Обе", age_category=None):
        """max_weight: число (55), строка '70+' для верхнего открытого класса,
        либо строка 'Absolute' — абсолютная категория без ограничения веса."""
        if isinstance(max_weight, str) and max_weight.strip().lower() == "absolute":
            is_plus = True
            numeric = 999999.0
        else:
            is_plus = isinstance(max_weight, str) and max_weight.endswith("+")
            numeric = float(str(max_weight).rstrip("+"))
        cur = self.conn.execute(
            "INSERT INTO weight_categories (tournament_id,name,max_weight,hand,is_plus,age_category) "
            "VALUES (?,?,?,?,?,?)",
            (tid, name, numeric, hand, int(is_plus), age_category))
        self.conn.commit()
        return cur.lastrowid

    def get_categories(self, tid):
        return self.conn.execute(
            "SELECT * FROM weight_categories WHERE tournament_id=? ORDER BY max_weight", (tid,)).fetchall()

    def delete_category(self, cid):
        self.conn.execute("DELETE FROM weight_categories WHERE id=?", (cid,))
        self.conn.commit()

    def add_participant(self, tid, name, weight, club, category_id, hand="Обе", photo_path="",
                        age_category="Senior", athlete_id=None):
        cur = self.conn.execute(
            "INSERT INTO participants (tournament_id,name,weight,club,category_id,hand,photo_path,age_category,athlete_id) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (tid, name, weight, club, category_id, hand, photo_path, age_category, athlete_id))
        self.conn.commit()
        return cur.lastrowid

    def add_athlete(self, first_name, last_name, birth_date, gender, club="", rank="", photo_path=""):
        cur = self.conn.execute(
            "INSERT INTO athletes (first_name,last_name,birth_date,gender,club,rank,photo_path) VALUES (?,?,?,?,?,?,?)",
            (first_name, last_name, birth_date, gender, club, rank, photo_path))
        self.conn.commit()
        return cur.lastrowid

    def update_athlete(self, aid, first_name, last_name, birth_date, gender, club, rank, photo_path):
        self.conn.execute(
            "UPDATE athletes SET first_name=?,last_name=?,birth_date=?,gender=?,club=?,rank=?,photo_path=? WHERE id=?",
            (first_name, last_name, birth_date, gender, club, rank, photo_path, aid))
        self.conn.commit()

    def delete_athlete(self, aid):
        # participants.athlete_id ссылается на athletes(id) БЕЗ ON DELETE —
        # если не отвязать/не удалить вручную, после удаления карточки в
        # participants останутся "битые" athlete_id, указывающие в никуда.
        #
        # Поведение зависит от статуса турнира, в котором участвовал спортсмен:
        #  - турнир АКТИВНЫЙ (не завершён) → запись участия удаляется целиком,
        #    спортсмена как будто там никогда не было (он больше не должен
        #    "висеть" в живом турнире после удаления из общего реестра);
        #  - турнир ЗАВЕРШЁН → запись участия остаётся как исторический архив,
        #    только сама карточка спортсмена отвязывается (athlete_id=NULL).
        rows = self.conn.execute(
            "SELECT p.id AS pid, p.category_id AS cid, t.status AS tstatus "
            "FROM participants p JOIN tournaments t ON t.id = p.tournament_id "
            "WHERE p.athlete_id=?", (aid,)).fetchall()

        for r in rows:
            if r["tstatus"] == "finished":
                continue  # оставляем запись, отвяжем athlete_id ниже
            pid = r["pid"]
            # Убираем участника из ещё не сыгранных поединков сетки, чтобы не
            # остались "битые" ссылки на удалённого участника.
            self.conn.execute(
                "UPDATE matches SET p1_id=NULL WHERE p1_id=? AND status='pending'", (pid,))
            self.conn.execute(
                "UPDATE matches SET p2_id=NULL WHERE p2_id=? AND status='pending'", (pid,))
            self.conn.execute("DELETE FROM dvoeborie_overrides WHERE pid=?", (pid,))
            self.conn.execute("DELETE FROM participants WHERE id=?", (pid,))

        self.conn.execute("UPDATE participants SET athlete_id=NULL WHERE athlete_id=?", (aid,))
        self.conn.execute("DELETE FROM athletes WHERE id=?", (aid,))
        self.conn.commit()

    def search_athletes(self, query=""):
        if query:
            like = f"%{query.lower()}%"
            return self.conn.execute(
                "SELECT * FROM athletes WHERE lower(first_name || ' ' || last_name) LIKE ? ORDER BY last_name",
                (like,)).fetchall()
        return self.conn.execute("SELECT * FROM athletes ORDER BY last_name").fetchall()

    def get_athlete(self, aid):
        return self.conn.execute("SELECT * FROM athletes WHERE id=?", (aid,)).fetchone()

    def get_eligible_categories(self, tid, birth_date, weight,gender, tournament_year=None):
        """Категории ЭТОГО турнира, куда спортсмен допущен по возрасту/полу."""
        natural = compute_age_category(birth_date, gender, tournament_year)
        return [c for c in self.get_categories(tid)
                if c["age_category"] and is_eligible_for_category(natural, c["age_category"])
                and (c["is_plus"] or c["max_weight"] >= weight)]
    def update_participant(self, pid, name, weight, club, category_id, hand, photo_path, age_category="Senior", athlete_id=None):
        self.conn.execute(
            "UPDATE participants SET name=?,weight=?,club=?,category_id=?,hand=?,photo_path=?,age_category=?, athlete_id=? WHERE id=?",
            (name, weight, club, category_id, hand, photo_path, age_category, athlete_id, pid))
        self.conn.commit()

    def get_participants(self, tid, category_id=None):
        if category_id:
            return self.conn.execute(
                "SELECT p.*, wc.name as cat_name FROM participants p "
                "LEFT JOIN weight_categories wc ON p.category_id=wc.id "
                "WHERE p.tournament_id=? AND p.category_id=? ORDER BY p.name",
                (tid, category_id)).fetchall()
        return self.conn.execute(
            "SELECT p.*, wc.name as cat_name FROM participants p "
            "LEFT JOIN weight_categories wc ON p.category_id=wc.id "
            "WHERE p.tournament_id=? ORDER BY p.name",
            (tid,)).fetchall()

    def delete_participant(self, pid):
        self.conn.execute("DELETE FROM participants WHERE id=?", (pid,))
        self.conn.commit()

    def get_participant_by_barcode(self, barcode_value):
        """Ищет участника по значению штрихкода."""
        pid = parse_barcode_value(barcode_value)
        if pid is None:
            return None
        return self.get_participant(pid)

    def save_match(self, match: dict):
        if match.get("id"):
            self.conn.execute("""UPDATE matches SET winner_id=?,p1_losses=?,p2_losses=?,status=?
                WHERE id=?""",
                (match["winner_id"], match["p1_losses"], match["p2_losses"],
                 match["status"], match["id"]))
        else:
            cur = self.conn.execute("""INSERT INTO matches
                (tournament_id,category_id,hand,round_name,bracket,match_order,
                p1_id,p2_id,winner_id,p1_losses,p2_losses,is_bye,status,
                win_next_id,win_next_slot,lose_next_id,lose_next_slot,stage)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (match["tournament_id"], match["category_id"], match["hand"],
                match["round_name"], match["bracket"], match["match_order"],
                match["p1_id"], match["p2_id"], match["winner_id"],
                match["p1_losses"], match["p2_losses"], match.get("is_bye", 0),
                match["status"],
                match.get("win_next_id"), match.get("win_next_slot", 1),
                match.get("lose_next_id"), match.get("lose_next_slot", 1),
                match.get("stage", 0)))
            match["id"] = cur.lastrowid
        self.conn.commit()
        return match["id"]

    def get_matches(self, category_id, hand):
        return self.conn.execute(
            "SELECT * FROM matches WHERE category_id=? AND hand=? ORDER BY stage, bracket, match_order",
            (category_id, hand)).fetchall()

    def clear_matches(self, category_id, hand):
        self.conn.execute("DELETE FROM matches WHERE category_id=? AND hand=?", (category_id, hand))
        self.conn.commit()

    def get_bracket_table_number(self, category_id, hand):
        """Ранее сохранённый организатором номер стола для этой сетки
        (категория+рука), или None, если трансляция на табло не включена."""
        row = self.conn.execute(
            "SELECT table_number FROM matches WHERE category_id=? AND hand=? "
            "AND table_number IS NOT NULL LIMIT 1",
            (category_id, hand)).fetchone()
        return row["table_number"] if row else None

    def set_bracket_table_number(self, category_id, hand, table_number):
        """Проставляет (или, если table_number=None, снимает) номер стола
        всем матчам данной сетки локально. Синхронизацию с сайтом делает
        вызывающий код (см. BracketWindow._apply_broadcast_settings)."""
        self.conn.execute(
            "UPDATE matches SET table_number=? WHERE category_id=? AND hand=?",
            (table_number, category_id, hand))
        self.conn.commit()

    def get_participant(self, pid):
        if not pid:
            return None
        return self.conn.execute("SELECT * FROM participants WHERE id=?", (pid,)).fetchone()

    def close(self):
        self.conn.close()


# ════════════════════════════════════════════════════════════════
#  ИНТЕГРАЦИЯ С ЦЕНТРАЛЬНОЙ БАЗОЙ (Этап 6, ARCHITECTURE.md §5)
#  ────────────────────────────────────────────────────────────────
#  Оборачивает методы Database, НЕ меняя ни строки в их логике: сначала
#  выполняется оригинальный метод (локальный SQLite работает как раньше,
#  без изменений и без сетевых задержек для судей/табло на самом турнире),
#  и только потом результат уходит в центральную PostgreSQL через FastAPI.
#  Любая ошибка синхронизации (нет сети и т.п.) НИКОГДА не мешает локальной
#  работе — она просто уходит в офлайн-очередь (sync/state.py) и
#  повторяется позже через sync_manager.flush_pending().
# ════════════════════════════════════════════════════════════════
from sync.sync_manager import sync_manager  # noqa: E402

_original_create_tournament = Database.create_tournament
_original_add_category = Database.add_category
_original_add_participant = Database.add_participant
_original_update_participant = Database.update_participant
_original_save_match = Database.save_match
_original_add_athlete = Database.add_athlete
_original_update_athlete = Database.update_athlete
_original_delete_tournament = Database.delete_tournament
_original_delete_category = Database.delete_category
_original_delete_participant = Database.delete_participant
_original_delete_athlete = Database.delete_athlete



def _synced_create_tournament(self, name, date, location="", weight_tolerance=0,
                              bracket_system="double", format_type="separate"):
    tid = _original_create_tournament(self, name, date, location, weight_tolerance,
                                      bracket_system, format_type)
    try:
        sync_manager.on_tournament_created(tid, name, date, location,
                                           weight_tolerance, bracket_system, format_type)
    except Exception as e:  # синк не должен ронять программу организатора
        print(f"[sync] create_tournament: {e}")
    return tid


def _synced_add_category(self, tid, name, max_weight, hand="Обе", age_category=None):
    cid = _original_add_category(self, tid, name, max_weight, hand, age_category)
    try:
        # Сервер ждёт max_weight числом (float|None). Локально "Absolute" и
        # "70+" тоже приводятся к числу в add_category — повторяем ту же
        # логику здесь, чтобы не слать на бэкенд сырые строки.
        if isinstance(max_weight, str) and max_weight.strip().lower() == "absolute":
            sync_max_weight = None
        else:
            sync_max_weight = float(str(max_weight).rstrip("+"))
        sync_manager.on_category_created(tid, cid, name, sync_max_weight, hand, age_category)
    except Exception as e:
        print(f"[sync] add_category: {e}")
    return cid


def _synced_add_participant(self, tid, name, weight, club, category_id, hand="Обе",
                             photo_path="", age_category="Senior", athlete_id=None):
    pid = _original_add_participant(self, tid, name, weight, club, category_id,
                                     hand, photo_path, age_category, athlete_id)
    try:
        sync_manager.on_participant_added(tid, pid, name, weight, club,
                                           category_id, hand, age_category,
                                           athlete_id=athlete_id)
    except Exception as e:
        print(f"[sync] add_participant: {e}")
    return pid


def _synced_update_participant(self, pid, name, weight, club, category_id, hand,
                                photo_path, age_category="Senior", athlete_id=None):
    _original_update_participant(self, pid, name, weight, club, category_id,
                                  hand, photo_path, age_category, athlete_id)
    try:
        sync_manager.on_participant_updated(pid, name, weight, club,
                                             category_id, hand, age_category)
    except Exception as e:
        print(f"[sync] update_participant: {e}")


def _synced_save_match(self, match: dict):
    is_update = bool(match.get("id"))
    snapshot = dict(match)
    mid = _original_save_match(self, match)
    try:
        if is_update:
            sync_manager.on_match_updated(mid, snapshot)
        else:
            sync_manager.on_match_created(mid, match)
    except Exception as e:
        print(f"[sync] save_match: {e}")
    return mid

def _synced_add_athlete(self, first_name, last_name, birth_date, gender,
                         club="", rank="", photo_path=""):
    aid = _original_add_athlete(self, first_name, last_name, birth_date,
                                 gender, club, rank, photo_path)
    try:
        sync_manager.on_athlete_created(aid, first_name, last_name,
                                         birth_date, gender, club, rank, photo_path)
    except Exception as e:
        print(f"[sync] add_athlete: {e}")
    return aid


def _synced_update_athlete(self, aid, first_name, last_name, birth_date,
                            gender, club, rank, photo_path):
    _original_update_athlete(self, aid, first_name, last_name, birth_date,
                              gender, club, rank, photo_path)
    try:
        sync_manager.on_athlete_updated(aid, first_name, last_name,
                                         birth_date, gender, club, rank, photo_path)
    except Exception as e:
        print(f"[sync] update_athlete: {e}")

def _synced_delete_tournament(self, tid):
    _original_delete_tournament(self, tid)
    try:
        sync_manager.on_tournament_deleted(tid)
    except Exception as e:
        print(f"[sync] delete_tournament: {e}")

def _synced_delete_category(self, cid):
    _original_delete_category(self, cid)
    try:
        sync_manager.on_category_deleted(cid)
    except Exception as e:
        print(f"[sync] delete_category: {e}")

def _synced_delete_participant(self, pid):
    _original_delete_participant(self, pid)
    try:
        sync_manager.on_participant_deleted(pid)
    except Exception as e:
        print(f"[sync] delete_participant: {e}")

def _synced_delete_athlete(self, aid):
    _original_delete_athlete(self, aid)
    try:
        sync_manager.on_athlete_deleted(aid)
    except Exception as e:
        print(f"[sync] delete_athlete: {e}")

Database.delete_tournament = _synced_delete_tournament
Database.delete_category = _synced_delete_category
Database.delete_participant = _synced_delete_participant
Database.create_tournament = _synced_create_tournament
Database.add_category = _synced_add_category
Database.add_participant = _synced_add_participant
Database.update_participant = _synced_update_participant
Database.save_match = _synced_save_match
Database.add_athlete = _synced_add_athlete
Database.update_athlete = _synced_update_athlete
Database.delete_athlete = _synced_delete_athlete


# ════
#  ГЕНЕРАТОР БЕЙДЖИКОВ С ШТРИХКОДАМИ
# ════

class BadgeGenerator:
    """Генерирует PDF с бейджиками участников (8 шт на A4)."""

    BADGE_W = 9 * cm
    BADGE_H = 6.2 * cm
    COLS = 2
    ROWS = 4
    MARGIN_LEFT = 1.5 * cm
    MARGIN_TOP = 2.5 * cm
    GAP_X = 0.5 * cm
    GAP_Y = 0.4 * cm

    @staticmethod
    def generate(filepath, tournament, participants, categories_map):
        """
        Генерирует PDF с бейджиками.
        participants: список dict-подобных объектов (sqlite3.Row)
        categories_map: {category_id: category_name}
        """
        if not REPORTLAB_AVAILABLE:
            raise RuntimeError("Установите reportlab: pip install reportlab")

        c = pdf_canvas.Canvas(filepath, pagesize=A4)
        page_w, page_h = A4

        badge_idx = 0
        total = len(participants)

        for i, p in enumerate(participants):
            col = badge_idx % BadgeGenerator.COLS
            row = (badge_idx // BadgeGenerator.COLS) % BadgeGenerator.ROWS

            x = BadgeGenerator.MARGIN_LEFT + col * (BadgeGenerator.BADGE_W + BadgeGenerator.GAP_X)
            y = page_h - BadgeGenerator.MARGIN_TOP - (row + 1) * BadgeGenerator.BADGE_H - row * BadgeGenerator.GAP_Y

            BadgeGenerator._draw_badge(c, x, y, p, tournament, categories_map)

            badge_idx += 1
            if badge_idx % (BadgeGenerator.COLS * BadgeGenerator.ROWS) == 0 and i < total - 1:
                c.showPage()
                badge_idx = 0

        c.save()

    @staticmethod
    def _draw_badge(c, x, y, participant, tournament, categories_map):
        bw = BadgeGenerator.BADGE_W
        bh = BadgeGenerator.BADGE_H

        # Фон и рамка
        c.setStrokeColor(colors.HexColor("#2a4a6c"))
        c.setLineWidth(1.5)
        c.setFillColor(colors.HexColor("#f8fafc"))
        c.roundRect(x, y, bw, bh, 8, fill=1, stroke=1)

        # Верхняя полоса (заголовок)
        c.setFillColor(colors.HexColor("#1a3a5c"))
        c.roundRect(x, y + bh - 1.4 * cm, bw, 1.4 * cm, 8, fill=1, stroke=0)
        # Закрываем нижние скругления заголовка
        c.rect(x, y + bh - 1.4 * cm, bw, 0.5 * cm, fill=1, stroke=0)

        # Название турнира
        c.setFillColor(colors.white)
        c.setFont("Arial-Bold", 8)
        t_name = str(tournament["name"])[:40] if tournament else "Турнир"
        c.drawCentredString(x + bw / 2, y + bh - 0.7 * cm, t_name)

        t_date = str(tournament["date"]) if tournament else ""
        c.setFont("Arial", 6)
        c.drawCentredString(x + bw / 2, y + bh - 1.1 * cm, t_date)

        # Имя участника (крупно)
        c.setFillColor(colors.HexColor("#111111"))
        c.setFont("Arial-Bold", 14)
        name = str(participant["name"])
        if len(name) > 24:
            c.setFont("Arial-Bold", 11)
        c.drawCentredString(x + bw / 2, y + bh - 2.1 * cm, name)

        # Клуб
        c.setFillColor(colors.HexColor("#555555"))
        c.setFont("Arial", 8)
        club = str(participant["club"]) if participant["club"] else "—"
        c.drawCentredString(x + bw / 2, y + bh - 2.7 * cm, f"Клуб: {club}")

        # Категория и вес
        cat_name = categories_map.get(participant["category_id"], "—")
        weight = participant["weight"] if participant["weight"] else "—"
        hand = participant["hand"] if participant["hand"] else "Обе"
        info_line = f"{cat_name}  |  {weight} кг  |  {hand}"
        c.setFont("Arial", 7)
        c.setFillColor(colors.HexColor("#336699"))
        c.drawCentredString(x + bw / 2, y + bh - 3.2 * cm, info_line)

        # Штрихкод
        barcode_value = get_barcode_value(participant["id"])
        barcode = Code128(barcode_value, barHeight=1.0 * cm, barWidth=1.1)
        barcode_width = barcode.width
        bx = x + (bw - barcode_width) / 2
        by = y + 0.6 * cm
        barcode.drawOn(c, bx, by)

        # Значение штрихкода текстом
        c.setFillColor(colors.HexColor("#333333"))
        c.setFont("Arial", 7)
        c.drawCentredString(x + bw / 2, y + 0.2 * cm, barcode_value)

        # Линия-разделитель (для вырезания)
        c.setStrokeColor(colors.HexColor("#cccccc"))
        c.setLineWidth(0.3)
        c.setDash(3, 3)
        c.line(x - 0.2 * cm, y, x + bw + 0.2 * cm, y)
        c.line(x - 0.2 * cm, y + bh, x + bw + 0.2 * cm, y + bh)
        c.line(x, y - 0.2 * cm, x, y + bh + 0.2 * cm)
        c.line(x + bw, y - 0.2 * cm, x + bw, y + bh + 0.2 * cm)
        c.setDash()


# ════
#  ДВИЖОК ТУРНИРНОЙ СЕТКИ (Double Elimination)
# ════

class _BatchConnProxy:
    """Прокси вокруг sqlite3.Connection, который глушит commit().

    sqlite3.Connection не позволяет подменить атрибут commit напрямую
    (read-only C-объект), поэтому вместо этого на время батч-операции
    подменяется self.db.conn целиком на этот прокси. execute()/fetchone()
    и т.п. прозрачно уходят в реальное соединение, а commit() ничего не
    делает — реальный commit() вызывается один раз в конце вызывающим
    кодом.
    """
    def __init__(self, real_conn):
        self._real = real_conn

    def commit(self):
        pass

    def __getattr__(self, name):
        return getattr(self._real, name)


def _run_batched_bracket_generation(db, impl_fn, *args):
    """Общая обвязка для generate_bracket у обоих движков (Double/Single
    Elimination).

    Решает две независимые проблемы, из-за которых генерация сетки
    "долго думает":
    1. Локальные записи в SQLite батчатся в один commit вместо сотен
       (см. _BatchConnProxy).
    2. Синхронизация каждого матча с сайтом (sync_manager.on_match_created)
       по умолчанию делает блокирующий HTTP-запрос на UI-потоке — для
       сетки на 32+ участников это десятки последовательных сетевых
       round-trip'ов (и до REQUEST_TIMEOUT_SECONDS=5с на каждый, если
       сеть барахлит). На время генерации включаем sync_manager.force_queue
       — тогда каждый матч мгновенно (локально) уходит в офлайн-очередь
       вместо реального запроса, а после того как сетка уже отрисована,
       очередь отправляется одним фоновым потоком через flush_pending(),
       не блокируя интерфейс организатора.
    """
    real_conn = db.conn
    db.conn = _BatchConnProxy(real_conn)
    prev_force_queue = getattr(sync_manager, "force_queue", False)
    sync_manager.force_queue = True
    try:
        impl_fn(*args)
    finally:
        db.conn = real_conn
        real_conn.commit()
        sync_manager.force_queue = prev_force_queue
        if sync_manager.enabled:
            Thread(target=sync_manager.flush_pending, daemon=True).start()


class DoubleEliminationEngine:
    """
    Реализация сетки double elimination для произвольного числа участников.
    """

    def __init__(self, db):
        self.db = db

    # ──── ГЕНЕРАЦИЯ СЕТКИ ────
    def generate_bracket(self, tournament_id, category_id, hand, participant_ids):
        _run_batched_bracket_generation(
            self.db, self._generate_bracket_impl,
            tournament_id, category_id, hand, participant_ids,
        )

    def _generate_bracket_impl(self, tournament_id, category_id, hand, participant_ids):
        self.db.clear_matches(category_id, hand)

        n = len(participant_ids)
        if n < 2:
            return

        # Размеры раундов WB без паддинга до степени двойки:
        round_sizes = [n]
        while round_sizes[-1] > 1:
            round_sizes.append(math.ceil(round_sizes[-1] / 2))
        # для n=5: [5, 3, 2, 1]

        wb_round_count = len(round_sizes) - 1
        wb_rounds = []

        # ── Раунд 1: реальные пары + максимум ОДИН bye (только если n нечётное) ──
        pool = participant_ids[:]
        num_real_matches = n // 2
        num_byes = n % 2   # 0 или 1 — вот исправление сути бага

        round0 = []
        if num_byes:
            bye_player = pool.pop(0)
            round0.append({"p1_id": bye_player, "p2_id": None, "is_bye": 1})
        for _ in range(num_real_matches):
            p1 = pool.pop(0)
            p2 = pool.pop(0)
            round0.append({"p1_id": p1, "p2_id": p2, "is_bye": 0})
        wb_rounds.append(round0)

        # ── Остальные раунды WB — пустые, заполнятся автоматически через propagate ──
        for cnt in round_sizes[2:]:
            wb_rounds.append([{"p1_id": None, "p2_id": None, "is_bye": 0} for _ in range(cnt)])   

        lb_round_count = max(0, 2 * (wb_round_count - 1))
        lb_rounds = []
        if lb_round_count > 0:
            lb_sizes = [1] * lb_round_count
            lb_sizes[0] = max(1, math.ceil(num_real_matches / 2))
            for k in range(1, wb_round_count - 1):
                wb_losers_k = len(wb_rounds[k])   # реальное число проигравших в WB-раунде k
                cross_idx = 2 * k - 1
                pure_idx = 2 * k
                lb_sizes[cross_idx] = max(lb_sizes[cross_idx - 1], wb_losers_k)
                lb_sizes[pure_idx] = max(1, math.ceil(lb_sizes[cross_idx] / 2))
            if lb_round_count >= 2:
                lb_sizes[-1] = lb_sizes[-2]
            for cnt in lb_sizes:
                lb_rounds.append([{"p1_id": None, "p2_id": None, "is_bye": 0} for _ in range(cnt)])

        W = wb_round_count
        L = lb_round_count
        wb_stage = {}
        lb_stage = {}
        stage = 0
        wb_stage[0] = stage
        for r in range(1, W):
            stage += 1
            wb_stage[r] = stage
            trigger = r - 1
            if L > 0:
                if trigger == 0:
                    stage += 1
                    lb_stage[0] = stage
                elif trigger <= W - 2:
                    stage += 1
                    lb_stage[2 * trigger - 1] = stage
                    stage += 1
                    lb_stage[2 * trigger] = stage
        if L > 0 and (L - 1) not in lb_stage:
            stage += 1
            lb_stage[L - 1] = stage
        gf_stage = stage + 1

        wb_ids = []
        for r, matches_in_round in enumerate(wb_rounds):
            row_ids = []
            round_name = self._wb_round_name(r, wb_round_count)
            for i, m in enumerate(matches_in_round):
                mid = self.db.save_match({
                    "tournament_id": tournament_id,
                    "category_id": category_id,
                    "hand": hand,
                    "round_name": round_name,
                    "bracket": "winners",
                    "match_order": i,
                    "p1_id": m["p1_id"],
                    "p2_id": m["p2_id"],
                    "winner_id": None,
                    "p1_losses": 0,
                    "p2_losses": 0,
                    "is_bye": m["is_bye"],
                    "stage": wb_stage.get(r, r),
                    "status": "pending" if not m["is_bye"] else "waiting",
                })
                row_ids.append(mid)
            wb_ids.append(row_ids)

        lb_ids = []
        for r, matches_in_round in enumerate(lb_rounds):
            row_ids = []
            round_name = f"LB Раунд {r + 1}"
            for i, m in enumerate(matches_in_round):
                mid = self.db.save_match({
                    "tournament_id": tournament_id,
                    "category_id": category_id,
                    "hand": hand,
                    "round_name": round_name,
                    "bracket": "losers",
                    "match_order": i,
                    "p1_id": None,
                    "p2_id": None,
                    "winner_id": None,
                    "p1_losses": 0,
                    "p2_losses": 0,
                    "is_bye": 0,
                    "stage": lb_stage.get(r, r),
                    "status": "waiting",
                })
                row_ids.append(mid)
            lb_ids.append(row_ids)

        gf1_id = self.db.save_match({
            "tournament_id": tournament_id, "category_id": category_id, "hand": hand,
            "round_name": "Гранд-финал", "bracket": "final", "match_order": 0,
            "p1_id": None, "p2_id": None, "winner_id": None, "stage": gf_stage,
            "p1_losses": 0, "p2_losses": 0, "is_bye": 0, "status": "waiting",
        })
        gf2_id = self.db.save_match({
            "tournament_id": tournament_id, "category_id": category_id, "hand": hand,
            "round_name": "Гранд-финал (переигровка)", "bracket": "final", "match_order": 1,
            "p1_id": None, "p2_id": None, "winner_id": None, "stage": gf_stage + 1,
            "p1_losses": 0, "p2_losses": 0, "is_bye": 0, "status": "waiting",
        })

        # ═══ СВЯЗИ МЕЖДУ МАТЧАМИ ═══
        for r in range(len(wb_ids) - 1):
            for i, mid in enumerate(wb_ids[r]):
                target_id = wb_ids[r + 1][i // 2]
                slot = (i % 2) + 1
                self._set_links(mid, win_next_id=target_id, win_next_slot=slot)

        wb_final_id = wb_ids[-1][0]
        self._set_links(wb_final_id, win_next_id=gf1_id, win_next_slot=1)

        if lb_round_count > 0:
            real_i = 0
            for mid in wb_ids[0]:
                m0 = self._get_match(mid)
                if m0["is_bye"]:
                    continue
                target_id = lb_ids[0][real_i // 2]
                slot = (real_i % 2) + 1
                self._set_links(mid, lose_next_id=target_id, lose_next_slot=slot)
                real_i += 1
            
            self._compute_and_apply_is_bye(wb_ids, lb_ids, gf1_id)

            for r in range(1, len(wb_ids) - 1):
                lb_target_round = (r - 1) * 2 + 1
                target_round = lb_ids[lb_target_round]
                prev_round = lb_ids[lb_target_round - 1]
                n_targets = len(target_round)

                prev_is_bye = [bool(self._get_match(mid)["is_bye"]) for mid in prev_round]

                wb_real = []
                wb_dead = []
                for i, mid in enumerate(wb_ids[r]):
                    if self._get_match(mid)["is_bye"]:
                        wb_dead.append(mid)
                    else:
                        wb_real.append(mid)

                bye_targets = [i for i, b in enumerate(prev_is_bye) if b]
                real_targets = [i for i, b in enumerate(prev_is_bye) if not b]

                assign_order = bye_targets + real_targets
                sources = wb_real + wb_dead

                for src_mid, target_idx in zip(sources, assign_order):
                    target_id = target_round[min(target_idx, n_targets - 1)]
                    self._set_links(src_mid, lose_next_id=target_id, lose_next_slot=2)

            lb_final_id = lb_ids[-1][0]                              # ← вот эта строка
            self._set_links(wb_final_id, lose_next_id=lb_final_id, lose_next_slot=2)   # ← и эта

            for r in range(len(lb_ids) - 1):
                cur = lb_ids[r]
                nxt = lb_ids[r + 1]
                if r % 2 == 0:
                    for i, mid in enumerate(cur):
                        target_id = nxt[i] if i < len(nxt) else nxt[-1]
                        self._set_links(mid, win_next_id=target_id, win_next_slot=1)
                else:
                    for i, mid in enumerate(cur):
                        target_idx = i // 2
                        target_id = nxt[target_idx] if target_idx < len(nxt) else nxt[-1]
                        slot = (i % 2) + 1
                        self._set_links(mid, win_next_id=target_id, win_next_slot=slot)

            self._set_links(lb_final_id, win_next_id=gf1_id, win_next_slot=2)
        else:
            self._set_links(wb_final_id, lose_next_id=gf1_id, lose_next_slot=2)

        self._set_links(gf1_id, win_next_id=gf2_id, win_next_slot=0)
        self._compute_and_apply_is_bye(wb_ids, lb_ids, gf1_id)

        self._collapse_chained_byes(wb_ids, lb_ids)
        # Помечаем ghost-матчи (оба участника None) как done
        for mid in wb_ids[0]:
            m0 = self._get_match(mid)
            if m0["p1_id"] is None and m0["p2_id"] is None:
                self.db.conn.execute(
                    "UPDATE matches SET status='done', is_bye=1 WHERE id=?", (mid,))
                self.db.conn.commit()

        for mid in wb_ids[0]:
            self._resolve_if_bye(mid)

        # Каскадное разрешение BYE: повторяем пока есть изменения
        self._cascade_resolve_byes(category_id, hand)
        self._resolve_all_byes(category_id, hand)

    def _cascade_resolve_byes(self, category_id, hand):
        """Каскадно разрешает BYE/ghost-матчи после генерации сетки."""
        for _ in range(30):
            changed = False
            all_matches = self.db.get_matches(category_id, hand)

            for m in all_matches:
                if m["bracket"] == "final" or m["status"] in ("done", "bye", "pending"):
                    continue

                has_player = bool(m["p1_id"] or m["p2_id"])

                # BYE с одним участником — автоматически продвигаем игрока дальше.
                if m["is_bye"] and has_player:
                    before_status = m["status"]
                    self._resolve_if_bye(m["id"])
                    after = self._get_match(m["id"])
                    if after and after["status"] != before_status:
                        changed = True
                    continue

                # Пустой waiting-матч без живых источников — служебный ghost-матч.
                if not m["p1_id"] and not m["p2_id"]:
                    has_live_source = any(
                        src["status"] not in ("done", "bye") and
                        (src["win_next_id"] == m["id"] or src["lose_next_id"] == m["id"])
                        for src in all_matches
                    )
                    if not has_live_source:
                        self.db.conn.execute(
                            "UPDATE matches SET status='done', is_bye=1 WHERE id=?", (m["id"],))
                        self.db.conn.commit()
                        changed = True

            if not changed:
                break

    # ──── СИДИНГ ────
    @staticmethod
    def _seed_order(size):
        order = [1]
        while len(order) < size:
            total = len(order) * 2 + 1
            new_order = []
            for x in order:
                new_order.append(x)
                new_order.append(total - x)
            order = new_order
        return [x - 1 for x in order]

    @staticmethod
    def _wb_round_name(r, total_rounds):
        names_from_end = {
            0: "Финал WB",
            1: "1/2 финала WB",
            2: "1/4 финала WB",
            3: "1/8 финала WB",
        }
        idx_from_end = total_rounds - 1 - r
        if idx_from_end in names_from_end:
            return names_from_end[idx_from_end]
        return f"WB Раунд {r + 1}"

    # ──── СЛУЖЕБНОЕ ────
    def _compute_and_apply_is_bye(self, wb_ids, lb_ids, gf1_id):
        arrivals = {}

        def slot_count(mid):
            if mid not in arrivals:
                arrivals[mid] = [0, 0]
            return arrivals[mid]

        for round_ids in wb_ids:
            for mid in round_ids:
                m = self._get_match(mid)
                a = slot_count(mid)
                a[0] = 1 if m["p1_id"] is not None else 0
                a[1] = 1 if m["p2_id"] is not None else 0

        def process(mid):
            m = self._get_match(mid)
            a = slot_count(mid)
            total = a[0] + a[1]
            is_bye = (total == 1)
            win_out = 1 if total >= 1 else 0
            lose_out = 1 if total == 2 else 0

            if bool(m["is_bye"]) != is_bye:
                self.db.conn.execute(
                    "UPDATE matches SET is_bye=? WHERE id=?", (1 if is_bye else 0, mid))

            if m["win_next_id"] and win_out and m["bracket"] != "final":
                slot = m["win_next_slot"] or 1
                if slot in (1, 2):
                    slot_count(m["win_next_id"])[slot - 1] += win_out
            if m["lose_next_id"] and lose_out:
                slot = m["lose_next_slot"] or 1
                if slot in (1, 2):
                    slot_count(m["lose_next_id"])[slot - 1] += lose_out

        for round_ids in wb_ids:
            for mid in round_ids:
                process(mid)
        for round_ids in lb_ids:
            for mid in round_ids:
                process(mid)
        if gf1_id:
            process(gf1_id)
        self.db.conn.commit()
    
    def _collapse_chained_byes(self, wb_ids, lb_ids):
        all_lb = [mid for round_ids in lb_ids for mid in round_ids]
        for mid in all_lb:
            m = self._get_match(mid)
            if not m["is_bye"]:
                continue
            for src_id in all_lb:
                src = self._get_match(src_id)
                if src["win_next_id"] == mid and src["is_bye"]:
                    self._set_links(src_id, win_next_id=m["win_next_id"], win_next_slot=m["win_next_slot"])
                    self.db.conn.execute(
                        "UPDATE matches SET status='done', is_bye=0, p1_id=NULL, p2_id=NULL WHERE id=?",
                        (mid,))
                    
    def _set_links(self, match_id, win_next_id=None, win_next_slot=None,
                   lose_next_id=None, lose_next_slot=None):
        cur = self.db.conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
        new_win_id = win_next_id if win_next_id is not None else cur["win_next_id"]
        new_win_slot = win_next_slot if win_next_slot is not None else cur["win_next_slot"]
        new_lose_id = lose_next_id if lose_next_id is not None else cur["lose_next_id"]
        new_lose_slot = lose_next_slot if lose_next_slot is not None else cur["lose_next_slot"]
        self.db.conn.execute(
            "UPDATE matches SET win_next_id=?, win_next_slot=?, lose_next_id=?, lose_next_slot=? WHERE id=?",
            (new_win_id, new_win_slot, new_lose_id, new_lose_slot, match_id))
        self.db.conn.commit()

    def _get_match(self, match_id):
        return self.db.conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()

    def _place_player(self, match_id, slot, player_id):
        if player_id is None:
            return
        m = self._get_match(match_id)
        col = "p1_id" if slot == 1 else "p2_id"
        if m[col] is not None:
            return
        self.db.conn.execute(f"UPDATE matches SET {col}=? WHERE id=?", (player_id, match_id))
        self.db.conn.commit()
        self._update_status_after_fill(match_id)

    def _update_status_after_fill(self, match_id):
        m = self._get_match(match_id)
        if m["status"] not in ("waiting",):
            return
        if m["p1_id"] and m["p2_id"]:
            self.db.conn.execute("UPDATE matches SET status='pending' WHERE id=?", (match_id,))
            self.db.conn.commit()
        elif (m["p1_id"] or m["p2_id"]) and m["bracket"] != "final":
            pass
        self._resolve_if_bye(match_id)

    def _resolve_if_bye(self, match_id):
        m = self._get_match(match_id)
        if m["status"] == "done":
            return
        if m["bracket"] == "final":
            return
        if m["is_bye"]:
            winner = m["p1_id"] if m["p1_id"] else m["p2_id"]
            if winner:
                self.db.conn.execute(
                    "UPDATE matches SET status='bye', winner_id=? WHERE id=?",
                    (winner, match_id))
                self.db.conn.commit()
                self._propagate(match_id, winner, loser_id=None, is_bye=True)

    def _propagate(self, match_id, winner_id, loser_id, is_bye=False):
        m = self._get_match(match_id)
        if m["win_next_id"] and winner_id:
            self._place_player(m["win_next_id"], m["win_next_slot"], winner_id)
        if m["lose_next_id"] and loser_id and not is_bye:
            self._place_player(m["lose_next_id"], m["lose_next_slot"], loser_id)

    # ──── ПРОВЕДЕНИЕ ПОЕДИНКОВ ────

    def _resolve_all_byes(self, category_id, hand):
        """Итеративно разрешает все BYE-матчи во всех ветках."""
        for _ in range(50):
            changed = False
            matches = self.db.get_matches(category_id, hand)
            for m in matches:
                if m["status"] in ("done", "bye"):
                    continue
                # Если is_bye и хотя бы один игрок есть — резолвим
                if m["is_bye"] and (m["p1_id"] or m["p2_id"]) and m["bracket"] != "final":
                    self._resolve_if_bye(m["id"])
                    m2 = self._get_match(m["id"])
                    if m2["status"] in ("done", "bye"):
                        changed = True
                    continue
                # Если waiting и оба слота никогда не получат игрока — ghost
                if m["status"] == "waiting" and not m["p1_id"] and not m["p2_id"]:
                    has_source = False
                    for src in matches:
                        if src["status"] in ("done", "bye"):
                            continue
                        if src["win_next_id"] == m["id"] or src["lose_next_id"] == m["id"]:
                            has_source = True
                            break
                    if not has_source and m["bracket"] != "final":
                        self.db.conn.execute(
                            "UPDATE matches SET status='done', is_bye=1 WHERE id=?", (m["id"],))
                        self.db.conn.commit()
                        changed = True
            if not changed:
                break

    def advance_winner(self, match_id, winner_id):
        m = self._get_match(match_id)
        if not m or m["status"] == "done":
            return
        loser_id = m["p2_id"] if winner_id == m["p1_id"] else m["p1_id"]

        self.db.conn.execute(
            "UPDATE matches SET winner_id=?, status='done' WHERE id=?",
            (winner_id, match_id))
        self.db.conn.commit()

        if m["bracket"] == "final" and m["round_name"] == "Гранд-финал":
            # Определяем у кого 0 поражений до этого матча (пришёл из верхней сетки)
            all_matches_before = self.db.get_matches(m["category_id"], m["hand"])
            def count_losses_before(pid):
                losses = 0
                for mm in all_matches_before:
                    if mm["status"] == "done" and mm["winner_id"] and mm["id"] != m["id"]:
                        loser = mm["p2_id"] if mm["winner_id"] == mm["p1_id"] else mm["p1_id"]
                        if loser == pid:
                            losses += 1
                return losses

            p1_losses = count_losses_before(m["p1_id"])
            p2_losses = count_losses_before(m["p2_id"])

            if p1_losses == 0:
                undefeated = m["p1_id"]
                defeated_once = m["p2_id"]
            elif p2_losses == 0:
                undefeated = m["p2_id"]
                defeated_once = m["p1_id"]
            else:
                undefeated = None
                defeated_once = None

            if undefeated and winner_id == defeated_once:
                # Непобеждённый проиграл — теперь у обоих по 1 поражению,
                # нужна переигровка (супер-финал)
                gf2 = self._get_match(m["win_next_id"])
                if gf2:
                    self.db.conn.execute(
                        "UPDATE matches SET p1_id=?, p2_id=?, status='pending', "
                        "round_name='Супер-финал (переигровка)' WHERE id=?",
                        (undefeated, defeated_once, gf2["id"]))
                    self.db.conn.commit()
            else:
                # Непобеждённый выиграл — турнир завершён, переигровка не нужна
                gf2 = self._get_match(m["win_next_id"])
                if gf2 and gf2["status"] not in ("done", "bye"):
                    self.db.conn.execute(
                        "UPDATE matches SET status='bye' WHERE id=?", (gf2["id"],))
                    self.db.conn.commit()
            return

        if m["bracket"] == "final" and "переигровка" in m["round_name"]:
            return

        self._propagate(match_id, winner_id, loser_id)
        self._resolve_all_byes(m["category_id"], m["hand"])

    # ──── ТЕКУЩИЙ / СЛЕДУЮЩИЙ МАТЧ ────
    def get_current_and_next_match(self, category_id, hand):
        matches = self.db.get_matches(category_id, hand)
        ready = [m for m in matches
                 if m["status"] == "pending" and m["p1_id"] and m["p2_id"]]
        if not ready:
            return None, None

        def sort_key(m):
            return (m["stage"], m["id"])
        
        ready.sort(key=sort_key)
        current = ready[0]
        nxt = ready[1] if len(ready) > 1 else None
        return current, nxt

    # ──── ПОИСК АКТИВНОГО МАТЧА ПО УЧАСТНИКУ ────
    def find_active_match_for_participant(self, category_id, hand, participant_id):
        """Ищет активный (pending) матч, в котором участвует данный участник.
        Возвращает (match, is_in_current) или (None, False)."""
        current, nxt = self.get_current_and_next_match(category_id, hand)
        if current and (current["p1_id"] == participant_id or current["p2_id"] == participant_id):
            return current, True
        return None, False

    # ──── ИТОГОВЫЕ РЕЗУЛЬТАТЫ ────
    def get_standings(self, category_id, hand):
        matches = self.db.get_matches(category_id, hand)
        if not matches:
            return []

        stats = OrderedDict()

        def ensure(pid):
            if pid is None:
                return
            if pid not in stats:
                stats[pid] = {"pid": pid, "wins": 0, "losses": 0,
                    "eliminated": False, "elim_round_score": -1}

        for m in matches:
            ensure(m["p1_id"])
            ensure(m["p2_id"])
            if m["status"] in ("done", "bye") and m["winner_id"]:
                winner = m["winner_id"]
                loser = m["p2_id"] if winner == m["p1_id"] else m["p1_id"]
                if m["status"] == "done":
                    ensure(winner)
                    stats[winner]["wins"] += 1
                    if loser:
                        ensure(loser)
                        stats[loser]["losses"] += 1
                        round_score = self._round_score(m)
                        if round_score > stats[loser]["elim_round_score"]:
                            stats[loser]["elim_round_score"] = round_score
                            stats[loser]["eliminated"] = True

        if not stats:
            return []

        gf_matches = [m for m in matches if m["bracket"] == "final" and m["status"] == "done"]
        champion = None
        runner_up = None
        if gf_matches:
            last_gf = gf_matches[-1]
            champion = last_gf["winner_id"]
            runner_up = last_gf["p2_id"] if champion == last_gf["p1_id"] else last_gf["p1_id"]
            if champion in stats:
                stats[champion]["eliminated"] = False
                stats[champion]["elim_round_score"] = 9999
            if runner_up in stats:
                stats[runner_up]["eliminated"] = True
                stats[runner_up]["elim_round_score"] = 99998

        ordered = sorted(
            stats.values(),
            key=lambda s: (
                0 if s["pid"] == champion else 1,
                -s["elim_round_score"],
                -s["wins"],
            )
        )

        result = []
        for i, s in enumerate(ordered):
            result.append({
                "pid": s["pid"],
                "wins": s["wins"],
                "losses": s["losses"],
                "place": i + 1,
            })
        return result

    @staticmethod
    def _round_score(match):
        bracket_weight = {"winners": 0, "losers": 100, "final": 200}
        base = bracket_weight.get(match["bracket"], 0)
        rn = match["round_name"]
        digits = "".join(ch for ch in rn if ch.isdigit())
        round_num = int(digits) if digits else 0
        return base + round_num


class DisplayServer:
    def __init__(self):
        # tables: dict keyed by table number string -> dict with keys:
        #   category, hand, current_match, next_match
        self.tables = {}
        self.app = Flask(__name__)

        def _render_table_block(tnum, data):
            cat = data.get("category", "")
            hand = data.get("hand", "")
            current = data.get("current_match", "Нет активного поединка")
            nxt = data.get("next_match", "Нет следующего поединка")
            return f"""
            <div class="table-block">
              <div class="table-title">СТОЛ {tnum}</div>
              <div class="category">Категория {cat}<br>{hand} рука</div>
              <div class="current">{current}</div>
              <div class="next-title">Следующий бой</div>
              <div class="next">{nxt}</div>
            </div>"""

        @self.app.route("/")
        def home():
            active = dict(self.tables)
            n = len(active)
            cols = min(n, 2) if n > 0 else 1

            blocks = ""
            for tnum in sorted(active.keys()):
                blocks += _render_table_block(tnum, active[tnum])

            if n == 0:
                blocks = "<div class='table-block'><div class='table-title'>Нет активных столов</div></div>"
                cols = 1

            title_size = "36px" if cols == 2 else "50px"
            cat_size = "22px" if cols == 2 else "32px"
            current_size = "58px" if cols == 2 else "80px"
            next_title_size = "24px" if cols == 2 else "36px"
            next_size = "38px" if cols == 2 else "55px"

            return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="2">
<title>Турнир</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: #111;
  color: white;
  font-family: Arial, sans-serif;
  min-height: 100vh;
}}
.grid {{
  display: grid;
  grid-template-columns: repeat({cols}, 1fr);
  gap: 16px;
  padding: 20px;
  min-height: calc(100vh - 50px);
}}
.table-block {{
  background: #1a1a1a;
  border: 1px solid #2a2a2a;
  border-radius: 16px;
  padding: 30px 24px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
}}
.table-title {{
  font-size: {title_size};
  color: #00ff88;
  font-weight: bold;
  letter-spacing: 2px;
}}
.category {{
  font-size: {cat_size};
  color: #ccddee;
  line-height: 1.5;
}}
.current {{
  font-size: {current_size};
  font-weight: bold;
  color: white;
  margin-top: 8px;
  line-height: 1.2;
}}
.next-title {{
  font-size: {next_title_size};
  color: #ffaa00;
  margin-top: 14px;
  font-weight: bold;
}}
.next {{
  font-size: {next_size};
  color: #dddd;
}}
.footer {{
  text-align: center;
  color: #445566;
  font-size: 13px;
  padding: 10px 0 14px 0;
}}
</style>
</head>
<body>
<div class="grid">
{blocks}
</div>
<div class="footer">Турнирная система: Double Elimination (до 2 поражений)</div>
</body>
</html>"""

    def update_table(self, table_num, category, hand, current_match, next_match):
        self.tables[str(table_num)] = {
            "category": category,
            "hand": hand,
            "current_match": current_match,
            "next_match": next_match,
        }

    def remove_table(self, table_num):
        self.tables.pop(str(table_num), None)

    def start(self):
        Thread(
            target=lambda: self.app.run(
                host="0.0.0.0",
                port=5000,
                debug=False,
                use_reloader=False
            ),
            daemon=True
        ).start()


# ════
#  ВИДЖЕТЫ
# ════
class ScrollableFrame(ctk.CTkScrollableFrame):
    pass


class ParticipantCard(ctk.CTkFrame):
    def __init__(self, master, participant, on_edit, on_delete, **kwargs):
        super().__init__(master, corner_radius=10, **kwargs)
        self.configure(fg_color=("#1e2a3a", "#1e2a3a"))
        p = participant

        photo_label = ctk.CTkLabel(self, text="👤", font=("Arial", 28), width=50)
        if PIL_AVAILABLE and p["photo_path"] and Path(p["photo_path"]).exists():
            try:
                img = Image.open(p["photo_path"]).resize((50, 60))
                photo = ctk.CTkImage(img, size=(50, 60))
                photo_label = ctk.CTkLabel(self, image=photo, text="")
                photo_label._image = photo
            except Exception:
                pass
        photo_label.grid(row=0, column=0, rowspan=3, padx=(10, 5), pady=10)

        ctk.CTkLabel(self, text=p["name"], font=ctk.CTkFont(size=14, weight="bold"),
                    anchor="w").grid(row=0, column=1, sticky="w", padx=5, pady=(8, 0))

        barcode_val = get_barcode_value(p["id"])
        info = f"⚖️ {p['weight']} кг   🏛 {p['club'] or '—'}   ✋ {p['hand'] or 'Обе'}   🔖 {barcode_val}"
        ctk.CTkLabel(self, text=info, font=ctk.CTkFont(size=11),
                    text_color="#8899aa", anchor="w").grid(row=1, column=1, sticky="w", padx=5)
        age_cat = p["age_category"] if "age_category" in p.keys() and p["age_category"] else "Senior"
        ctk.CTkLabel(self, text=f"Категория: {p['cat_name'] or '—'}   |   {age_cat}",
                    font=ctk.CTkFont(size=11), text_color="#5588bb",
                    anchor="w").grid(row=2, column=1, sticky="w", padx=5, pady=(0, 8))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=0, column=2, rowspan=3, padx=10, pady=10, sticky="e")
        ctk.CTkButton(btn_frame, text="✏️", width=36, height=32,
                    command=lambda: on_edit(p["id"])).pack(pady=2)
        ctk.CTkButton(btn_frame, text="🗑", width=36, height=32,
                    fg_color="#8b1a1a", hover_color="#a03030",
                    command=lambda: on_delete(p["id"])).pack(pady=2)
        self.columnconfigure(1, weight=1)

class ParticipantGroupCard(ctk.CTkFrame):
    """Одна карточка на спортсмена. Если он зарегистрирован в нескольких
    категориях этого турнира, все они показываются внутри ОДНОЙ карточки
    отдельными строками (со своим весом/хватом/штрихкодом на каждую),
    вместо того чтобы дублировать карточку целиком на каждую категорию."""

    PHOTO_W, PHOTO_H = 68, 82

    def __init__(self, master, participants, on_edit, on_delete, **kwargs):
        super().__init__(master, corner_radius=12, **kwargs)
        self.configure(fg_color=("#1e2a3a", "#1e2a3a"))
        first = participants[0]

        # ── фото — фиксированный размер, обрезаем по центру под рамку,
        #    чтобы карточки не "прыгали" от формы исходного файла ──
        photo_holder = ctk.CTkFrame(self, width=self.PHOTO_W, height=self.PHOTO_H,
                    corner_radius=8, fg_color="#0d1420")
        photo_holder.grid(row=0, column=0, rowspan=len(participants) + 1,
                          padx=(14, 10), pady=14, sticky="n")
        photo_holder.grid_propagate(False)
        photo_holder.columnconfigure(0, weight=1)
        photo_holder.rowconfigure(0, weight=1)

        photo_label = ctk.CTkLabel(photo_holder, text="👤",
                    font=("Arial", 30), text_color="#556677")
        if PIL_AVAILABLE and first["photo_path"] and Path(first["photo_path"]).exists():
            try:
                img = Image.open(first["photo_path"])
                img = ImageOps.exif_transpose(img)
                img = ImageOps.fit(img, (self.PHOTO_W, self.PHOTO_H), Image.LANCZOS)
                photo = ctk.CTkImage(img, size=(self.PHOTO_W, self.PHOTO_H))
                photo_label = ctk.CTkLabel(photo_holder, image=photo, text="")
                photo_label._image = photo
            except Exception:
                pass
        photo_label.grid(row=0, column=0, sticky="nsew")

        # ── имя + клуб + возрастная категория — общие для спортсмена,
        #    показываются один раз, а не на каждую весовую категорию ──
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=(10, 4))
        header.columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text=first["name"], font=ctk.CTkFont(size=15, weight="bold"),
                    anchor="w").grid(row=0, column=0, sticky="w")

        age_cat = first["age_category"] if "age_category" in first.keys() and first["age_category"] else "Senior"
        club_text = f"🏛 {first['club'] or '—'}   🎂 {age_cat}"
        ctk.CTkLabel(header, text=club_text, font=ctk.CTkFont(size=11),
                    text_color="#8899aa", anchor="w").grid(row=1, column=0, sticky="w")

        if len(participants) > 1:
            ctk.CTkLabel(header, text=f"⚔ {len(participants)} категории",
                    font=ctk.CTkFont(size=11, weight="bold"), text_color="#ffaa00",
                    fg_color="#2a2205", corner_radius=8
                    ).grid(row=0, column=1, rowspan=2, sticky="e", padx=(10, 0))

        # ── отдельная строка на каждую весовую категорию ──
        for i, p in enumerate(participants):
            row = ctk.CTkFrame(self, fg_color="#141b26" if i % 2 == 0 else "#171f2c",
                                corner_radius=8)
            row.grid(row=i + 1, column=1, sticky="ew", padx=(0, 10), pady=2)
            row.columnconfigure(0, weight=1)

            barcode_val = get_barcode_value(p["id"])
            info = f"⚖️ {p['weight']} кг   ✋ {p['hand'] or 'Обе'}   🔖 {barcode_val}"

            ctk.CTkLabel(row, text=p["cat_name"] or "—", font=ctk.CTkFont(size=12, weight="bold"),
                    text_color="#5588bb", anchor="w"
                    ).grid(row=0, column=0, sticky="w", padx=10, pady=(6, 0))
            ctk.CTkLabel(row, text=info, font=ctk.CTkFont(size=11),
                    text_color="#8899aa", anchor="w"
                    ).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 6))

            btns = ctk.CTkFrame(row, fg_color="transparent")
            btns.grid(row=0, column=1, rowspan=2, padx=8, pady=4, sticky="e")
            ctk.CTkButton(btns, text="✏️", width=32, height=28,
                    command=lambda pid=p["id"]: on_edit(pid)).pack(side="left", padx=2)
            ctk.CTkButton(btns, text="🗑", width=32, height=28,
                    fg_color="#8b1a1a", hover_color="#a03030",
                    command=lambda pid=p["id"]: on_delete(pid)).pack(side="left", padx=2)

        self.columnconfigure(1, weight=1)

# ════
#  SINGLE ELIMINATION (до одного поражения)
# ════
class SingleEliminationEngine:
    """
    Обычная сетка на выбывание. Использует ту же таблицу matches, что и
    DoubleEliminationEngine (win_next_id/win_next_slot), но lose_next_*
    не используются — проигравший просто выбывает.
    """

    def __init__(self, db):
        self.db = db

    def generate_bracket(self, tournament_id, category_id, hand, participant_ids):
        _run_batched_bracket_generation(
            self.db, self._generate_bracket_impl,
            tournament_id, category_id, hand, participant_ids,
        )

    def _generate_bracket_impl(self, tournament_id, category_id, hand, participant_ids):
        self.db.clear_matches(category_id, hand)

        n = len(participant_ids)
        if n < 2:
            return

        pool = participant_ids[:]

        # ── раунд 0: реальные пары + BYE только если n нечётное (максимум 1) ──
        round0 = []
        if n % 2:
            p = pool.pop(0)
            round0.append({"p1_id": p, "p2_id": None, "is_bye": 1})
        for _ in range(len(pool) // 2):
            p1 = pool.pop(0)
            p2 = pool.pop(0)
            round0.append({"p1_id": p1, "p2_id": p2, "is_bye": 0})

        rounds = [round0]

        # ── каждый следующий раунд: BYE ставится только если из предыдущего
        #    раунда выходит нечётное число победителей — и только в ОДНОМ,
        #    последнем матче этого раунда. Никаких заранее заготовленных
        #    "лишних" BYE в глубину сетки. ──
        prev_count = len(round0)
        while prev_count > 1:
            cnt = math.ceil(prev_count / 2)
            needs_bye = (prev_count % 2 == 1)
            round_matches = []
            for i in range(cnt):
                is_bye = 1 if (needs_bye and i == cnt - 1) else 0
                round_matches.append({"p1_id": None, "p2_id": None, "is_bye": is_bye})
            rounds.append(round_matches)
            prev_count = cnt

        round_count = len(rounds)

        ids = []
        for r, matches_in_round in enumerate(rounds):
            row_ids = []
            round_name = self._round_name(r, round_count)
            for i, m in enumerate(matches_in_round):
                mid = self.db.save_match({
                    "tournament_id": tournament_id,
                    "category_id": category_id,
                    "hand": hand,
                    "round_name": round_name,
                    "bracket": "winners",
                    "match_order": i,
                    "p1_id": m["p1_id"],
                    "p2_id": m["p2_id"],
                    "winner_id": None,
                    "p1_losses": 0,
                    "p2_losses": 0,
                    "is_bye": m["is_bye"],
                    "stage": r,
                    "status": "pending" if not m["is_bye"] else "waiting",
                })
                row_ids.append(mid)
            ids.append(row_ids)

        for r in range(len(ids) - 1):
            for i, mid in enumerate(ids[r]):
                target_id = ids[r + 1][i // 2]
                slot = (i % 2) + 1
                self._set_links(mid, win_next_id=target_id, win_next_slot=slot)

        for mid in ids[0]:
            m0 = self._get_match(mid)
            if m0["p1_id"] is None and m0["p2_id"] is None:
                self.db.conn.execute(
                    "UPDATE matches SET status='done', is_bye=1 WHERE id=?", (mid,))
                self.db.conn.commit()

        for mid in ids[0]:
            self._resolve_if_bye(mid)

        self._resolve_all_byes(category_id, hand)

    @staticmethod
    def _round_name(r, total_rounds):
        remaining = total_rounds - r
        if remaining == 1:
            return "Финал"
        if remaining == 2:
            return "Полуфинал"
        if remaining == 3:
            return "1/4 финала"
        return f"Раунд {r + 1}"

    def _set_links(self, match_id, win_next_id=None, win_next_slot=None):
        cur = self.db.conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
        new_win_id = win_next_id if win_next_id is not None else cur["win_next_id"]
        new_win_slot = win_next_slot if win_next_slot is not None else cur["win_next_slot"]
        self.db.conn.execute(
            "UPDATE matches SET win_next_id=?, win_next_slot=? WHERE id=?",
            (new_win_id, new_win_slot, match_id))
        self.db.conn.commit()

    def _get_match(self, match_id):
        return self.db.conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()

    def _place_player(self, match_id, slot, player_id):
        if player_id is None:
            return
        m = self._get_match(match_id)
        col = "p1_id" if slot == 1 else "p2_id"
        if m[col] is not None:
            return
        self.db.conn.execute(f"UPDATE matches SET {col}=? WHERE id=?", (player_id, match_id))
        self.db.conn.commit()
        self._update_status_after_fill(match_id)

    def _update_status_after_fill(self, match_id):
        m = self._get_match(match_id)
        if m["status"] != "waiting":
            return
        if m["p1_id"] and m["p2_id"]:
            self.db.conn.execute("UPDATE matches SET status='pending' WHERE id=?", (match_id,))
            self.db.conn.commit()
        self._resolve_if_bye(match_id)

    def _resolve_if_bye(self, match_id):
        m = self._get_match(match_id)
        if m["status"] == "done":
            return
        if m["is_bye"]:
            winner = m["p1_id"] if m["p1_id"] else m["p2_id"]
            if winner:
                self.db.conn.execute(
                    "UPDATE matches SET status='bye', winner_id=? WHERE id=?",
                    (winner, match_id))
                self.db.conn.commit()
                if m["win_next_id"]:
                    self._place_player(m["win_next_id"], m["win_next_slot"], winner)

    def _resolve_all_byes(self, category_id, hand):
        for _ in range(50):
            changed = False
            matches = self.db.get_matches(category_id, hand)
            for m in matches:
                if m["status"] in ("done", "bye"):
                    continue
                if m["is_bye"] and (m["p1_id"] or m["p2_id"]):
                    self._resolve_if_bye(m["id"])
                    m2 = self._get_match(m["id"])
                    if m2["status"] in ("done", "bye"):
                        changed = True
            if not changed:
                break

    def advance_winner(self, match_id, winner_id):
        m = self._get_match(match_id)
        if not m or m["status"] == "done":
            return
        self.db.conn.execute(
            "UPDATE matches SET winner_id=?, status='done' WHERE id=?",
            (winner_id, match_id))
        self.db.conn.commit()

        if m["win_next_id"]:
            self._place_player(m["win_next_id"], m["win_next_slot"], winner_id)
        self._resolve_all_byes(m["category_id"], m["hand"])

    def get_current_and_next_match(self, category_id, hand):
        matches = self.db.get_matches(category_id, hand)
        ready = [m for m in matches
                 if m["status"] == "pending" and m["p1_id"] and m["p2_id"]]
        if not ready:
            return None, None
        ready.sort(key=lambda m: (m["stage"], m["id"]))
        current = ready[0]
        nxt = ready[1] if len(ready) > 1 else None
        return current, nxt

    def find_active_match_for_participant(self, category_id, hand, participant_id):
        current, nxt = self.get_current_and_next_match(category_id, hand)
        if current and (current["p1_id"] == participant_id or current["p2_id"] == participant_id):
            return current, True
        return None, False

    def get_standings(self, category_id, hand):
        matches = self.db.get_matches(category_id, hand)
        if not matches:
            return []

        stats = OrderedDict()

        def ensure(pid):
            if pid is None:
                return
            if pid not in stats:
                stats[pid] = {"pid": pid, "wins": 0, "losses": 0,
                    "eliminated": False, "elim_round_score": -1}

        for m in matches:
            ensure(m["p1_id"])
            ensure(m["p2_id"])
            if m["status"] in ("done", "bye") and m["winner_id"]:
                winner = m["winner_id"]
                loser = m["p2_id"] if winner == m["p1_id"] else m["p1_id"]
                if m["status"] == "done":
                    ensure(winner)
                    stats[winner]["wins"] += 1
                    if loser:
                        ensure(loser)
                        stats[loser]["losses"] += 1
                        if m["stage"] > stats[loser]["elim_round_score"]:
                            stats[loser]["elim_round_score"] = m["stage"]
                            stats[loser]["eliminated"] = True

        if not stats:
            return []

        final_matches = [m for m in matches if m["win_next_id"] is None and m["status"] == "done"]
        champion = None
        if final_matches:
            last = max(final_matches, key=lambda m: m["stage"])
            champion = last["winner_id"]
            if champion in stats:
                stats[champion]["eliminated"] = False
                stats[champion]["elim_round_score"] = 9999

        return sorted(
            stats.values(),
            key=lambda s: (
                0 if s["pid"] == champion else 1,
                -s["elim_round_score"],
                s["losses"],
            )
        )


def _standings_with_place(engine, category_id, hand):
    """Возвращает get_standings(...), гарантируя ключ 'place' в каждой строке
    (SingleEliminationEngine его не проставляет, в отличие от Double)."""
    standings = engine.get_standings(category_id, hand)
    out = []
    for i, s in enumerate(standings):
        row = dict(s)
        if row.get("place") is None:
            row["place"] = i + 1
        out.append(row)
    return out


def compute_dvoeborie_standings(db, engine, category):
    """Сводный зачёт ДВОЕБОРЬЯ (левая рука + правая рука) для весовой категории.

    Место, занятое спортсменом на каждой руке, переводится в очки по таблице
    DVOEBORIE_POINTS (10,7,5,4,3,2,1,0,0...), очки суммируются, и по убыванию
    суммы очков строится итоговая расстановка мест. Спортсмены, выбывшие
    раньше остальных на обеих руках, автоматически получают меньше очков и
    оказываются внизу списка — т.е. полная расстановка мест "снизу вверх"
    получается сама собой, без отдельной ручной сортировки выбывших.

    Возвращает список словарей, отсортированный по итоговому месту:
        pid, name, club, right_place, right_points,
        left_place, left_points, total_points, place
    """
    right = _standings_with_place(engine, category["id"], "Правая")
    left = _standings_with_place(engine, category["id"], "Левая")

    right_map = {s["pid"]: s for s in right}
    left_map = {s["pid"]: s for s in left}

    pids = set(right_map) | set(left_map)
    rows = []
    for pid in pids:
        p = db.get_participant(pid)
        if not p:
            continue
        r = right_map.get(pid)
        l = left_map.get(pid)
        r_place = r["place"] if r else None
        l_place = l["place"] if l else None
        r_pts = get_dvoeborie_points(r_place)
        l_pts = get_dvoeborie_points(l_place)
        rows.append({
            "pid": pid,
            "name": p["name"],
            "club": p["club"] if "club" in p.keys() and p["club"] else "—",
            "right_place": r_place,
            "left_place": l_place,
            "right_points": r_pts,
            "left_points": l_pts,
            "total_points": r_pts + l_pts,
            "weight": p["weight"],
        })

    def best_place(row):
        places = [x for x in (row["right_place"], row["left_place"]) if x]
        return min(places) if places else 9999

    # Больше очков — выше; при равенстве очков — у кого было лучшее место
    # на какой-либо руке; иначе — по имени (стабильность порядка).
    rows.sort(key=lambda r: (-r["total_points"], r["weight"], best_place(r), r["name"]))


    # Итоговое место: спортивная (конкурентная) расстановка —
    # равные суммы очков получают одно и то же место.
    place = 0
    prev_points = None
    for i, row in enumerate(rows):
        if row["total_points"] != prev_points:
            place = i + 1
            prev_points = row["total_points"]
        row["place"] = place
    return rows


# ════
#  ОКНО СЕТКИ (с поддержкой сканера)
# ════
class BracketWindow(ctk.CTkToplevel):
    def __init__(self, master, db, tournament_id, category, hand):
        super().__init__(master)
        self.withdraw()
        self.db = db
        self.tournament_id = tournament_id
        self.category = category
        self.hand = hand
        tournament = db.get_tournament(tournament_id)
        bracket_system = tournament["bracket_system"] if tournament and "bracket_system" in tournament.keys() else "double"
        self.engine = SingleEliminationEngine(db) if bracket_system == "single" else DoubleEliminationEngine(db)

        if not hasattr(master, "_open_bracket_windows"):
            master._open_bracket_windows = []
        master._open_bracket_windows.append(self)

        # Номер стола / трансляция на табло сайта — раньше назначались
        # автоматически (жёстко только "1" или "2" по числу открытых окон),
        # из-за чего нельзя было ни выбрать конкретный стол, ни выключить
        # трансляцию конкретной категории. Теперь это ручной выбор
        # организатора (см. _build_broadcast_bar / _apply_broadcast_settings),
        # который сохраняется локально и переживает закрытие окна.
        self.table_number = db.get_bracket_table_number(category["id"], hand)

        self.title(f"Сетка — {category['name']} — {hand}")
        self.geometry("1200x800")
        self.configure(fg_color="#0d1117")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self.safe_init)

    def _on_close(self):
        app = self.master
        if hasattr(app, "display_server") and self.table_number is not None:
            app.display_server.remove_table(self.table_number)
        if hasattr(app, "_open_bracket_windows"):
            try:
                app._open_bracket_windows.remove(self)
            except ValueError:
                pass
        self.destroy()

    def safe_init(self):
        try:
            self._build_ui()
            self._load_bracket()
            self._assign_table_number()
            self.deiconify()
            self.update_idletasks()
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Ошибка сетки", str(e))
            self.destroy()

    def _build_ui(self):
        top = ctk.CTkFrame(self, fg_color="#161b22", height=55)
        top.pack(fill="x", padx=0, pady=0)
        top.pack_propagate(False)

        title_text = f"🏆  {self.category['name']}  |  {self.hand}  |  До 2 поражений"
        locked = self.db.is_tournament_finished(self.tournament_id)
        if locked:
            title_text += "   🔒 ТУРНИР ЗАВЕРШЁН — ТОЛЬКО ПРОСМОТР"
        title_label_kwargs = {"text_color": "#ff8866"} if locked else {}
        ctk.CTkLabel(top, text=title_text,
                    font=ctk.CTkFont(size=15, weight="bold"),
                    **title_label_kwargs
                    ).pack(side="left", padx=20)

        ctk.CTkButton(top, text="⚡ Создать сетку", width=140, height=34,
                    state="disabled" if locked else "normal",
                    command=self._generate).pack(side="right", padx=10, pady=10)
        ctk.CTkButton(top, text="🗑 Сбросить сетку", width=140, height=34,
                    fg_color="#4a1a1a", hover_color="#6a2a2a",
                    state="disabled" if locked else "normal",
                    command=self._reset_bracket).pack(side="right", padx=5, pady=10)
        ctk.CTkButton(top, text="📄 Протокол PDF", width=140, height=34,
                    fg_color="#1a4a2a", hover_color="#2a6a3a",
                    command=self._export_pdf).pack(side="right", padx=5, pady=10)

        # ── Панель текущего / следующего поединка ──
        self.match_info_bar = ctk.CTkFrame(self, fg_color="#0d1f30", height=48)
        self.match_info_bar.pack(fill="x", padx=0, pady=0)
        self.match_info_bar.pack_propagate(False)
        self.lbl_current = ctk.CTkLabel(
            self.match_info_bar,
            text="⚔️  Текущий поединок: —",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#4dccff", anchor="w")
        self.lbl_current.pack(side="left", padx=20, pady=10)
        self.lbl_next = ctk.CTkLabel(
            self.match_info_bar,
            text="⏭  Следующий: —",
            font=ctk.CTkFont(size=12),
            text_color="#aabbcc", anchor="w")
        self.lbl_next.pack(side="left", padx=30, pady=10)

        self._build_broadcast_bar()

        # ════
        #  ПАНЕЛЬ СКАНЕРА ШТРИХКОДОВ
        # ════
        self.scanner_frame = ctk.CTkFrame(self, fg_color="#0a1520", height=60)
        self.scanner_frame.pack(fill="x", padx=0, pady=0)
        self.scanner_frame.pack_propagate(False)

        ctk.CTkLabel(
            self.scanner_frame,
            text="📷 СКАНЕР:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#ffaa00"
        ).pack(side="left", padx=(20, 10), pady=10)

        self.scan_entry = ctk.CTkEntry(
            self.scanner_frame,
            width=250,
            height=36,
            placeholder_text="Сканируйте штрихкод победителя...",
            font=ctk.CTkFont(size=14)
        )
        self.scan_entry.pack(side="left", padx=5, pady=10)
        self.scan_entry.bind("<Return>", self._on_scan_enter)

        ctk.CTkButton(
            self.scanner_frame,
            text="✅ Подтвердить",
            width=120, height=36,
            fg_color="#1a5a2a", hover_color="#2a7a3a",
            command=lambda: self._on_scan_enter(None)
        ).pack(side="left", padx=5, pady=10)

        self.scan_status_label = ctk.CTkLabel(
            self.scanner_frame,
            text="",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#888888",
            anchor="w"
        )
        self.scan_status_label.pack(side="left", padx=20, pady=10, fill="x", expand=True)

        # Автофокус на поле сканера
        self.scan_entry.focus_set()
        self.bind("<FocusIn>", lambda e: self.scan_entry.focus_set())

        self.tabs = ctk.CTkTabview(self, fg_color="#0d1117")
        self.tabs.pack(fill="both", expand=True, padx=5, pady=5)
        self.tabs.add("🏟 Сетка")
        self.tabs.add("📋 Поединки")
        self.tabs.add("🥇 Итоги")

        bracket_outer = self.tabs.tab("🏟 Сетка")
        self.canvas_frame = ctk.CTkFrame(bracket_outer, fg_color="#0d1117")
        self.canvas_frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(self.canvas_frame, bg="#0d1117",
                    highlightthickness=0, cursor="crosshair")
        hscroll = ctk.CTkScrollbar(self.canvas_frame, orientation="horizontal",
                    command=self.canvas.xview)
        vscroll = ctk.CTkScrollbar(self.canvas_frame, orientation="vertical",
                    command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hscroll.set, yscrollcommand=vscroll.set)
        hscroll.pack(side="bottom", fill="x")
        vscroll.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True)

        match_tab = self.tabs.tab("📋 Поединки")
        self.match_scroll = ScrollableFrame(match_tab, fg_color="#0d1117")
        self.match_scroll.pack(fill="both", expand=True, padx=10, pady=10)

        result_tab = self.tabs.tab("🥇 Итоги")
        self.result_frame = ctk.CTkFrame(result_tab, fg_color="#0d1117")
        self.result_frame.pack(fill="both", expand=True, padx=10, pady=10)
    
    # ════
    #  ОБРАБОТКА СКАНИРОВАНИЯ ШТРИХКОДА
    # ════
    def _on_scan_enter(self, event):
        """Вызывается при нажатии Enter в поле сканера."""
        barcode_value = self.scan_entry.get().strip()
        if not barcode_value:
            return

        self.scan_entry.delete(0, "end")

        # 1. Парсим штрихкод
        pid = parse_barcode_value(barcode_value)
        if pid is None:
            self._show_scan_status("❌ Неверный формат штрихкода!", "#ff4444")
            return

        # 2. Находим участника
        participant = self.db.get_participant(pid)
        if not participant:
            self._show_scan_status(f"❌ Участник с ID {pid} не найден!", "#ff4444")
            return

        # 3. Проверяем текущий активный поединок
        current, _ = self.engine.get_current_and_next_match(
            self.category["id"], self.hand)

        if not current:
            self._show_scan_status(
                f"⚠️ {participant['name']} — нет активного поединка!", "#ffaa00")
            return

        # 4. Проверяем, участвует ли в текущем матче
        if pid == current["p1_id"] or pid == current["p2_id"]:
            # ПОБЕДИТЕЛЬ!
            self.engine.advance_winner(current["id"], pid)
            self._show_scan_status(
                f"🏆 ПОБЕДИТЕЛЬ: {participant['name']}!", "#00ff88")
            self._load_bracket()
        else:
            # Не в текущем матче
            self._show_scan_status(
                f"⚠️ {participant['name']} не участвует в текущем поединке!", "#ffaa00")

        # Возвращаем фокус на поле ввода
        self.scan_entry.focus_set()

    def _show_scan_status(self, text, color):
        """Показывает статус сканирования и сбрасывает через 4 секунды."""
        self.scan_status_label.configure(text=text, text_color=color)
        # Мигающий эффект
        if hasattr(self, "_scan_flash_id"):
            self.after_cancel(self._scan_flash_id)
        self._scan_flash_id = self.after(4000, lambda: self.scan_status_label.configure(
            text="", text_color="#888888"))

    # ────
    def _refresh_match_info_bar(self):
        def pname(pid):
            if not pid:
                return "?"
            p = self.db.get_participant(pid)
            return p["name"] if p else "?"

        current, nxt = self.engine.get_current_and_next_match(
            self.category["id"], self.hand)

        if current:
            txt = (f"⚔️  {pname(current['p1_id'])}  vs  {pname(current['p2_id'])}")
            self.lbl_current.configure(text=txt, text_color="#4dccff")
        else:
            matches = self.db.get_matches(self.category["id"], self.hand)
            if not matches:
                self.lbl_current.configure(text="⚔️  Сетка не создана", text_color="#556677")
            else:
                pending_any = [m for m in matches if m["status"] == "pending"]
                if pending_any:
                    self.lbl_current.configure(
                        text="⏳  Ожидание участников для следующего поединка...",
                        text_color="#ffaa33")
                else:
                    finals = [m for m in matches if m["bracket"] == "final" and m["status"] == "done"]
                    if finals:
                        winner = pname(finals[-1]["winner_id"])
                        self.lbl_current.configure(
                            text=f"🏆  Турнир завершён! Победитель: {winner}",
                            text_color="#ffd700")
                    else:
                        self.lbl_current.configure(
                            text="✅  Все поединки завершены", text_color="#4dff88")

        if nxt:
            txt_n = (f"⏭  {pname(nxt['p1_id'])}  vs  {pname(nxt['p2_id'])}")
            self.lbl_next.configure(text=txt_n, text_color="#aabbcc")
        else:
            self.lbl_next.configure(text="⏭  Следующий: —", text_color="#445566")

        app = self.master
        if hasattr(app, "display_server") and self.table_number is not None:
            app.display_server.update_table(
                self.table_number,
                self.category["name"],
                self.hand,
                self.lbl_current.cget("text"),
                self.lbl_next.cget("text"),
            )

    def _load_bracket(self):
        self._refresh_match_info_bar()
        self._draw_bracket()
        self._render_match_list()
        self._render_results()

    def _tournament_locked(self, show_warning=True):
        """True, если турнир этой сетки завершён — редактирование запрещено."""
        locked = self.db.is_tournament_finished(self.tournament_id)
        if locked and show_warning:
            messagebox.showwarning("Турнир завершён",
                    "Турнир завершён — изменения недоступны.\n"
                    "Можно только просматривать сетку и результаты.")
        return locked

    def _generate(self):
        if self._tournament_locked():
            return
        all_participants = self.db.get_participants(self.tournament_id, self.category["id"])
        participants = [p for p in all_participants if p["hand"] in (self.hand, "Обе")]
        if len(participants) < 2:
            messagebox.showwarning("Мало участников", "Нужно минимум 2 участника в категории.")
            return
        if not messagebox.askyesno("Создать сетку",
                    f"Будет создана сетка для {len(participants)} участников.\n"
                    "Все текущие результаты будут удалены. Продолжить?"):
            return
        import random
        ids = [p["id"] for p in participants]
        # Сид зависит только от турнира и категории (БЕЗ hand), чтобы левая
        # и правая рука одной категории получали ОДИНАКОВЫЙ порядок пар.
        rng = random.Random(f"{self.tournament_id}-{self.category['id']}")
        rng.shuffle(ids)
        self.engine.generate_bracket(self.tournament_id, self.category["id"], self.hand, ids)
        self._load_bracket()
        self._assign_table_number()

    def _assign_table_number(self):
        """Проставляет self.table_number всем матчам этой категории/руки —
        локально (чтобы выбор организатора пережил переоткрытие окна и
        пересоздание сетки) и на сайте, чтобы там можно было собрать живую
        очередь пар по столам (см. sync_manager.on_matches_table_assigned).
        table_number=None корректно снимает трансляцию с обеих сторон."""
        self.db.set_bracket_table_number(self.category["id"], self.hand, self.table_number)
        try:
            matches = self.db.get_matches(self.category["id"], self.hand)
            mids = [m["id"] for m in matches]
            if mids:
                sync_manager.on_matches_table_assigned(mids, self.table_number)
        except Exception as e:
            print(f"[sync] assign_table: {e}")

    def _suggest_table_number(self):
        """Первый свободный номер стола среди остальных открытых сеток,
        которые сейчас транслируются на табло."""
        used = {
            w.table_number for w in getattr(self.master, "_open_bracket_windows", [])
            if w is not self and w.winfo_exists() and w.table_number is not None
        }
        n = 1
        while n in used:
            n += 1
        return n

    def _find_broadcast_conflict(self, table_number):
        """Название другой открытой сетки, уже транслирующей этот номер
        стола (или None). Два РАЗНЫХ поединка на одном номере стола
        перемешаются в одну очередь на публичном табло (см. /queue —
        группировка идёт по table_number), поэтому перед подтверждением
        стоит предупредить организатора."""
        for w in getattr(self.master, "_open_bracket_windows", []):
            if w is self or not w.winfo_exists():
                continue
            if w.table_number == table_number:
                return f"{w.category['name']} — {w.hand}"
        return None

    def _refresh_broadcast_status_label(self):
        if not hasattr(self, "broadcast_status_label"):
            return
        if self.table_number is None:
            self.broadcast_status_label.configure(text="не транслируется на сайте")
        else:
            self.broadcast_status_label.configure(
                text=f"транслируется на /board — стол {self.table_number}")

    def _apply_broadcast_settings(self, table_number):
        self.table_number = table_number
        self._assign_table_number()
        self._refresh_broadcast_status_label()

    def _build_broadcast_bar(self):
        """Переключатель \"выводить эту сетку на публичное табло сайта /
        какой стол\" — раньше это решалось само (первые два открытых окна
        автоматически получали стол 1/2 и всегда транслировались), теперь
        организатор выбирает явно и выбор сохраняется локально."""
        bar = ctk.CTkFrame(self, fg_color="#141a10", height=44)
        bar.pack(fill="x", padx=0, pady=0)
        bar.pack_propagate(False)

        self.broadcast_var = ctk.BooleanVar(value=self.table_number is not None)

        def on_toggle():
            if self.broadcast_var.get():
                table_num = self.table_number or self._suggest_table_number()
                conflict = self._find_broadcast_conflict(table_num)
                if conflict and not messagebox.askyesno(
                        "Стол уже занят",
                        f"Стол {table_num} уже транслирует «{conflict}». "
                        "Продолжить с тем же номером? (пары перемешаются на табло)"):
                    table_num = self._suggest_table_number()
                self.table_entry.configure(state="normal")
                self.table_entry.delete(0, "end")
                self.table_entry.insert(0, str(table_num))
                self._apply_broadcast_settings(table_num)
            else:
                self.table_entry.configure(state="disabled")
                self._apply_broadcast_settings(None)

        ctk.CTkCheckBox(
            bar, text="📡 Транслировать на табло сайта", variable=self.broadcast_var,
            command=on_toggle, font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left", padx=(20, 10), pady=8)

        ctk.CTkLabel(bar, text="Стол №", font=ctk.CTkFont(size=12)).pack(side="left", padx=(10, 4))
        self.table_entry = ctk.CTkEntry(bar, width=50, height=28)
        self.table_entry.pack(side="left", padx=(0, 10))
        if self.table_number is not None:
            self.table_entry.insert(0, str(self.table_number))
        else:
            self.table_entry.configure(state="disabled")

        def on_table_changed(event=None):
            if not self.broadcast_var.get():
                return
            raw = self.table_entry.get().strip()
            if not raw.isdigit() or int(raw) < 1:
                messagebox.showwarning("Некорректный номер", "Номер стола — положительное целое число.")
                self.table_entry.delete(0, "end")
                self.table_entry.insert(0, str(self.table_number or 1))
                return
            new_num = int(raw)
            if new_num == self.table_number:
                return
            conflict = self._find_broadcast_conflict(new_num)
            if conflict and not messagebox.askyesno(
                    "Стол уже занят",
                    f"Стол {new_num} уже транслирует «{conflict}». "
                    "Одновременная трансляция двух категорий на одном столе "
                    "перемешает пары на публичном табло. Всё равно продолжить?"):
                self.table_entry.delete(0, "end")
                self.table_entry.insert(0, str(self.table_number or 1))
                return
            self._apply_broadcast_settings(new_num)

        self.table_entry.bind("<FocusOut>", on_table_changed)
        self.table_entry.bind("<Return>", on_table_changed)

        self.broadcast_status_label = ctk.CTkLabel(
            bar, text="", font=ctk.CTkFont(size=11), text_color="#77aa88")
        self.broadcast_status_label.pack(side="left", padx=10)
        self._refresh_broadcast_status_label()

    def _reset_bracket(self):
        if self._tournament_locked():
            return
        if not messagebox.askyesno("Сбросить сетку",
                    "Все результаты поединков будут удалены. Продолжить?"):
            return
        self.db.clear_matches(self.category["id"], self.hand)
        self._load_bracket()
        messagebox.showinfo("Готово", "Сетка сброшена.")

    # ────
    def _draw_bracket(self):
        self.canvas.delete("all")
        # Определяем реальный текущий матч через движок
        _cur, _nxt = self.engine.get_current_and_next_match(self.category["id"], self.hand)
        self._current_match_id = _cur["id"] if _cur else None
        self._next_match_id = _nxt["id"] if _nxt else None
        matches = self.db.get_matches(self.category["id"], self.hand)
        if not matches:
            self.canvas.create_text(400, 200,
                    text="Сетка ещё не создана.\nНажмите «Создать сетку»",
                    fill="#445566", font=("Arial", 16), justify="center")
            return

        from collections import OrderedDict
        w_rounds = OrderedDict()
        l_rounds = OrderedDict()
        f_rounds = OrderedDict()
        for m in matches:
            b = m["bracket"]
            r = m["round_name"]
            if b == "winners":
                w_rounds.setdefault(r, []).append(m)
            elif b == "losers":
                l_rounds.setdefault(r, []).append(m)
            else:   
                f_rounds.setdefault(r, []).append(m)

        BOX_W, BOX_H = 200, 52
        H_GAP = 36
        SLOT_H = BOX_H + 14
        X_START = 20
        Y_W_START = 60

        w_rounds_list = list(w_rounds.values())
        if not w_rounds_list:
            return

        def y_pos(match_idx, round_idx):
            step = SLOT_H * (2 ** round_idx)
            first_center = Y_W_START + (SLOT_H * (2 ** round_idx) - BOX_H) / 2
            return first_center + match_idx * step

        w_col_x = []
        w_y_positions = []

        for ri, rmatches in enumerate(w_rounds_list):
            x = X_START + ri * (BOX_W + H_GAP)
            col_ys = []
            for mi, m in enumerate(rmatches):
                y = y_pos(mi, ri)
                self._draw_match_box(m, x, y, BOX_W, BOX_H)
                col_ys.append(y)
                if ri + 1 < len(w_rounds_list):
                    x_mid = x + BOX_W + H_GAP // 2
                    y_center = y + BOX_H // 2
                    self.canvas.create_line(x + BOX_W, y_center, x_mid, y_center,
                        fill="#2a4a6a", width=1)
            w_col_x.append(x)
            w_y_positions.append(col_ys)
            if ri + 1 < len(w_rounds_list) and len(col_ys) >= 2:
                x_mid = x + BOX_W + H_GAP // 2
                x_next = x + BOX_W + H_GAP
                for pair in range(0, len(col_ys), 2):
                    if pair + 1 < len(col_ys):
                        y1 = col_ys[pair] + BOX_H // 2
                        y2 = col_ys[pair + 1] + BOX_H // 2
                        y_mid = (y1 + y2) // 2
                        self.canvas.create_line(x_mid, y1, x_mid, y2, fill="#2a4a6a", width=1)
                        self.canvas.create_line(x_mid, y_mid, x_next, y_mid, fill="#2a4a6a", width=1)

        x_final = X_START + len(w_rounds_list) * (BOX_W + H_GAP)
        y_final = Y_W_START
        for fi, (rname, rmatches) in enumerate(f_rounds.items()):
            x_this = x_final + fi * (BOX_W + H_GAP)   # ← сдвиг вправо вместо вниз
            for m in rmatches:
                is_reset = "переигровка" in m["round_name"]
                if is_reset and not (m["p1_id"] and m["p2_id"]) and m["status"] != "done":
                    continue
                self._draw_match_box(m, x_this, y_final, BOX_W, BOX_H, highlight="#3a3010")
                if w_col_x:
                    x_prev = w_col_x[-1] + BOX_W
                    x_mid = x_prev + H_GAP // 2
                    y_wf = w_y_positions[-1][0] + BOX_H // 2 if w_y_positions and w_y_positions[-1] else y_final + BOX_H // 2
                    y_f = y_final + BOX_H // 2
                    self.canvas.create_line(x_prev, y_wf, x_mid, y_wf, fill="#8a6a10", width=1)
                    self.canvas.create_line(x_mid, y_wf, x_mid, y_f, fill="#8a6a10", width=1)
                    self.canvas.create_line(x_mid, y_f, x_this, y_f, fill="#8a6a10", width=1)

        max_y_w = Y_W_START
        for col_ys in w_y_positions:
            for y in col_ys:
                max_y_w = max(max_y_w, y + BOX_H)

        Y_L_START = max_y_w + 50
        l_rounds_list = list(l_rounds.values())

        if l_rounds_list:
            self.canvas.create_text(
                X_START, Y_L_START - 22,
                text="⬇  НИЖНЯЯ СЕТКА (Losers Bracket)",
                fill="#cc6633", font=("Arial", 11, "bold"), anchor="w")

            # Вычисляем позиции матчей нижней сетки с правильным вертикальным расположением.
            # В нечётных раундах (0,2,4…) приходят проигравшие из верхней сетки — матчи
            # расположены попарно и занимают вдвое больше места, чем в предыдущем раунде.
            # В чётных раундах (1,3,5…) победители уплотняются вдвое.
            # Базовый шаг вертикали берём из первого раунда нижней сетки.

            L_SLOT_H = BOX_H + 14   # шаг для первого раунда нижней сетки
            l_col_positions = []     # list of list of (x, y) per round

            for ri, rmatches in enumerate(l_rounds_list):
                x = X_START + (ri + 1) * (BOX_W + H_GAP)
                # Шаг растёт вдвое каждые два раунда (после объединяющих раундов)
                step_mult = 2 ** (ri // 2)
                step = L_SLOT_H * step_mult
                # Центрируем первый матч относительно всей высоты первого раунда
                total_first = L_SLOT_H * max(len(l_rounds_list[0]), 1)
                first_offset = (step - L_SLOT_H) // 2
                col_ys = []
                for mi, m in enumerate(rmatches):
                    y = Y_L_START + first_offset + mi * step
                    self._draw_match_box(m, x, y, BOX_W, BOX_H, highlight="#2a1510")
                    col_ys.append(y)
                l_col_positions.append((x, col_ys))

            # Соединительные линии между раундами нижней сетки.
            # Тип перехода определяется по РЕАЛЬНЫМ размерам раундов (а не по чётности
            # индекса), чтобы точно соответствовать фактической маршрутизации матчей
            # (win_next_id) для любого числа участников.
            LINE_COLOR = "#7a3a1a"
            for ri in range(len(l_col_positions) - 1):
                x_cur, ys_cur = l_col_positions[ri]
                x_nxt, ys_nxt = l_col_positions[ri + 1]
                x_out = x_cur + BOX_W
                x_mid = x_out + H_GAP // 2
                x_in = x_nxt

                is_merging_round = len(ys_nxt) < len(ys_cur)

                if is_merging_round:
                    # Объединяющий раунд: каждые два матча → один следующий
                    for pair_start in range(0, len(ys_cur), 2):
                        if pair_start + 1 < len(ys_cur):
                            y1 = ys_cur[pair_start] + BOX_H // 2
                            y2 = ys_cur[pair_start + 1] + BOX_H // 2
                            target_idx = pair_start // 2
                            if target_idx < len(ys_nxt):
                                y_target = ys_nxt[target_idx] + BOX_H // 2
                                # горизонталь от текущих матчей до середины
                                self.canvas.create_line(x_out, y1, x_mid, y1,
                                    fill=LINE_COLOR, width=1)
                                self.canvas.create_line(x_out, y2, x_mid, y2,
                                    fill=LINE_COLOR, width=1)
                                # вертикаль, соединяющая пару
                                self.canvas.create_line(x_mid, y1, x_mid, y2,
                                    fill=LINE_COLOR, width=1)
                                # горизонталь к следующему матчу
                                self.canvas.create_line(x_mid, y_target, x_in, y_target,
                                    fill=LINE_COLOR, width=1)
                        elif pair_start < len(ys_cur):
                            # нечётное число — одиночный матч идёт напрямую
                            y1 = ys_cur[pair_start] + BOX_H // 2
                            target_idx = pair_start // 2
                            if target_idx < len(ys_nxt):
                                y_target = ys_nxt[target_idx] + BOX_H // 2
                                self.canvas.create_line(x_out, y1, x_mid, y1,
                                    fill=LINE_COLOR, width=1)
                                self.canvas.create_line(x_mid, y1, x_mid, y_target,
                                    fill=LINE_COLOR, width=1)
                                self.canvas.create_line(x_mid, y_target, x_in, y_target,
                                    fill=LINE_COLOR, width=1)
                elif len(ys_nxt) > len(ys_cur):
                    # Расширяющийся переход (не должен встречаться в норме, но
                    # обрабатываем на всякий случай): матчи распределяются 1-к-1
                    # по первым соответствующим позициям следующего раунда.
                    for mi_cur, y_cur in enumerate(ys_cur):
                        if mi_cur < len(ys_nxt):
                            y_from = y_cur + BOX_H // 2
                            y_to = ys_nxt[mi_cur] + BOX_H // 2
                            self.canvas.create_line(x_out, y_from, x_mid, y_from,
                                fill=LINE_COLOR, width=1)
                            self.canvas.create_line(x_mid, y_from, x_mid, y_to,
                                fill=LINE_COLOR, width=1)
                            self.canvas.create_line(x_mid, y_to, x_in, y_to,
                                fill=LINE_COLOR, width=1)
                else:
                    # Раунд приёма: каждый матч → один следующий (1-к-1)
                    for mi_cur, y_cur in enumerate(ys_cur):
                        if mi_cur < len(ys_nxt):
                            y_from = y_cur + BOX_H // 2
                            y_to = ys_nxt[mi_cur] + BOX_H // 2
                            self.canvas.create_line(x_out, y_from, x_mid, y_from,
                                fill=LINE_COLOR, width=1)
                            self.canvas.create_line(x_mid, y_from, x_mid, y_to,
                                fill=LINE_COLOR, width=1)
                            self.canvas.create_line(x_mid, y_to, x_in, y_to,
                                fill=LINE_COLOR, width=1)

        total_w = x_final + len(f_rounds) * (BOX_W + H_GAP) + 60
        if l_rounds_list:
            x_l_end = X_START + (len(l_rounds_list) + 1) * (BOX_W + H_GAP) + 60
            total_w = max(total_w, x_l_end)
            # Высота: берём максимум по всем раундам нижней сетки
            max_l_y = Y_L_START
            for ri, rmatches in enumerate(l_rounds_list):
                step_mult = 2 ** (ri // 2)
                step = (BOX_H + 14) * step_mult
                first_offset = (step - (BOX_H + 14)) // 2
                bottom = Y_L_START + first_offset + (len(rmatches) - 1) * step + BOX_H
                max_l_y = max(max_l_y, bottom)
            total_h = max_l_y + 60
        else:
            total_h = max_y_w + 60
        self.canvas.configure(scrollregion=(0, 0, total_w, total_h))

    def _draw_match_box(self, m, x, y, w, h, highlight=None):
        c = self.canvas
        is_current = (m["id"] == getattr(self, "_current_match_id", None))
        is_next = (not is_current) and (m["id"] == getattr(self, "_next_match_id", None))

        bg = highlight or "#1a2a3a"
        outline_color = "#2a3f55"
        outline_w = 1

        if is_current:
            bg = "#103820"
            outline_color = "#00ff88"
            outline_w = 3
            c.create_rectangle(x - 4, y - 4, x + w + 4, y + h + 4,
                        outline="#00ff88", width=2)
        elif is_next:
            outline_color = "#ffaa33"
            outline_w = 2
        c.create_rectangle(x, y, x + w, y + h, fill=bg, outline=outline_color, width=outline_w)

        def pname(pid):
            if pid:
                p = self.db.get_participant(pid)
                return p["name"] if p else "?"
            # Слот пуст. Если матч структурно является BYE (один участник
            # гарантированно отсутствует) — честно пишем "BYE". Но если матч
            # НЕ является BYE, слот просто ждёт победителя ещё не сыгранного
            # предыдущего матча — писать "BYE" тут неверно и вводит в
            # заблуждение (создаёт впечатление, что соперник уже прошёл
            # автоматически, хотя предыдущий матч ещё не завершён).
            if m["is_bye"]:
                return "BYE"
            return "— ожидание —"

        p1n = pname(m["p1_id"])
        p2n = pname(m["p2_id"])
        winner_id = m["winner_id"]

        p1_color = "#ffffff"
        p2_color = "#ffffff"
        if winner_id:
            if winner_id == m["p1_id"]:
                p1_color = "#4dff88"
                p2_color = "#ff5555"
            else:
                p1_color = "#ff5555"
                p2_color = "#4dff88"

        c.create_line(x + 1, y + h // 2, x + w - 1, y + h // 2, fill="#2a3f55", width=1)
        c.create_text(x + 6, y + h // 4, text=p1n[:22], fill=p1_color,
                    font=("Arial", 9, "bold"), anchor="w")
        c.create_text(x + 6, y + 3 * h // 4, text=p2n[:22], fill=p2_color,
                    font=("Arial", 9, "bold"), anchor="w")
        c.create_text(x + w - 4, y + 4, text=m["round_name"],
                    fill="#556677", font=("Arial", 7), anchor="ne")

        tag = f"match_{m['id']}"
        c.create_rectangle(x, y, x + w, y + h, fill="", outline="", tags=(tag,))
        c.tag_bind(tag, "<Button-1>", lambda e, mid=m["id"]: self._open_result_dialog(mid))

    def _open_result_dialog(self, match_id):
        if self._tournament_locked():
            return
        m = self.db.conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
        if not m:
            return
        if m["status"] == "bye":
            return
        if not m["p1_id"] or not m["p2_id"]:
            self.canvas.delete("popup")
            self.canvas.create_text(
                400, 40, text="⏳ Участники ещё не определены",
                fill="#ffaa33", font=("Arial", 12, "bold"), tags="popup")
            self.after(2000, lambda: self.canvas.delete("popup"))
            return

        p1 = self.db.get_participant(m["p1_id"])
        p2 = self.db.get_participant(m["p2_id"])
        if not p1 or not p2:
            return

        self.canvas.delete("popup")
        cx = self.canvas.winfo_width() // 2
        cy = self.canvas.winfo_height() // 2
        pw, ph = 320, 160
        x0, y0 = cx - pw // 2, cy - ph // 2
        x1, y1 = cx + pw // 2, cy + ph // 2

        self.canvas.create_rectangle(x0 - 2, y0 - 2, x1 + 2, y1 + 2,
                    fill="#4a8fc4", outline="", tags="popup")
        self.canvas.create_rectangle(x0, y0, x1, y1,
                    fill="#0d1f30", outline="", tags="popup")
        self.canvas.create_text(cx, y0 + 22,
                    text=f"Раунд {m['round_name']} — кто победил?",
                    fill="#aaccee", font=("Arial", 11, "bold"), tags="popup")

        bh = 36
        b1y0, b1y1 = y0 + 44, y0 + 44 + bh
        r1 = self.canvas.create_rectangle(x0 + 10, b1y0, x1 - 10, b1y1,
                    fill="#1a5a2a", outline="#2a8a3a", width=1, tags="popup")
        t1 = self.canvas.create_text(cx, (b1y0 + b1y1) // 2,
                    text=f"🏆  {p1['name'][:28]}",
                    fill="#ffffff", font=("Arial", 11, "bold"), tags="popup")

        b2y0, b2y1 = b1y1 + 8, b1y1 + 8 + bh
        r2 = self.canvas.create_rectangle(x0 + 10, b2y0, x1 - 10, b2y1,
                    fill="#1a5a2a", outline="#2a8a3a", width=1, tags="popup")
        t2 = self.canvas.create_text(cx, (b2y0 + b2y1) // 2,
                    text=f"🏆  {p2['name'][:28]}",
                    fill="#ffffff", font=("Arial", 11, "bold"), tags="popup")

        bc_y = b2y1 + 14
        tc = self.canvas.create_text(cx, bc_y, text="✕ Отмена", fill="#778899",
                    font=("Arial", 10), tags="popup")

        def set_winner(winner_id):
            self.canvas.delete("popup")
            self.engine.advance_winner(match_id, winner_id)
            self._load_bracket()

        def close_popup(e=None):
            self.canvas.delete("popup")

        def hover_in(rid):
            self.canvas.itemconfig(rid, fill="#2a7a3a")

        def hover_out(rid):
            self.canvas.itemconfig(rid, fill="#1a5a2a")

        for item in (r1, t1):
            self.canvas.tag_bind(item, "<Button-1>",
                    lambda e, wid=m["p1_id"]: set_winner(wid))
            self.canvas.tag_bind(item, "<Enter>", lambda e: hover_in(r1))
            self.canvas.tag_bind(item, "<Leave>", lambda e: hover_out(r1))

        for item in (r2, t2):
            self.canvas.tag_bind(item, "<Button-1>",
                    lambda e, wid=m["p2_id"]: set_winner(wid))
            self.canvas.tag_bind(item, "<Enter>", lambda e: hover_in(r2))
            self.canvas.tag_bind(item, "<Leave>", lambda e: hover_out(r2))

        self.canvas.tag_bind(tc, "<Button-1>", close_popup)
        self.canvas.tag_bind(tc, "<Enter>",
                    lambda e: self.canvas.itemconfig(tc, fill="#ffffff"))
        self.canvas.tag_bind(tc, "<Leave>",
                    lambda e: self.canvas.itemconfig(tc, fill="#778899"))

    # ────
    def _render_match_list(self):
        for w in self.match_scroll.winfo_children():
            w.destroy()
        matches = self.db.get_matches(self.category["id"], self.hand)
        if not matches:
            ctk.CTkLabel(self.match_scroll, text="Сетка не создана",
                    text_color="#445566").pack(pady=20)
            return

        current, _ = self.engine.get_current_and_next_match(self.category["id"], self.hand)
        current_id = current["id"] if current else None

        headers = ["Раунд", "Bracket", "Участник 1", "Участник 2", "Победитель", "Статус"]
        header_frame = ctk.CTkFrame(self.match_scroll, fg_color="#1a2535")
        header_frame.pack(fill="x", padx=2, pady=(0, 2))
        for i, h in enumerate(headers):
            ctk.CTkLabel(header_frame, text=h,
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color="#7799bb", width=120,
                    anchor="w").grid(row=0, column=i, padx=6, pady=6, sticky="w")

        def pname(pid, m=None):
            if pid:
                p = self.db.get_participant(pid)
                return p["name"] if p else "?"
            if m is not None and m["is_bye"]:
                return "BYE"
            return "— ожидание —"

        status_map = {
            "done": ("✅ Завершён", "#4dff88"),
            "pending": ("⏳ Ожидает", "#ffaa33"),
            "bye": ("⏭ Автовыход", "#778899"),
            "waiting": ("🔒 Не начат", "#445566")
        }
        bracket_map = {"winners": "Winners", "losers": "Losers", "final": "Финал"}

        for row_i, m in enumerate(matches):
            is_cur = (m["id"] == current_id)
            if is_cur:
                bg = "#0d2a1a"
            else:
                bg = "#0f1a25" if row_i % 2 == 0 else "#111e2d"
            fr = ctk.CTkFrame(self.match_scroll, fg_color=bg, height=38)
            fr.pack(fill="x", padx=2, pady=1)

            winner_name = pname(m["winner_id"]) if m["winner_id"] else "—"
            st_text, st_color = status_map.get(m["status"], (m["status"], "#ffffff"))

            marker = "▶ " if is_cur else ""
            row_data = [
                marker + m["round_name"],
                bracket_map.get(m["bracket"], m["bracket"]),
                pname(m["p1_id"], m), pname(m["p2_id"], m),
                winner_name, st_text
            ]
            colors_list = [
                "#00ff88" if is_cur else "#ccddee",
                "#998877", "#ffffff", "#ffffff", "#4dff88", st_color
            ]
            for i, (val, col) in enumerate(zip(row_data, colors_list)):
                ctk.CTkLabel(fr, text=str(val)[:22], text_color=col,
                    font=ctk.CTkFont(size=11), width=120,
                    anchor="w").grid(row=0, column=i, padx=6, pady=4, sticky="w")

    # ────
    def _render_results(self):
        for w in self.result_frame.winfo_children():
            w.destroy()
        standings = self.engine.get_standings(self.category["id"], self.hand)
        if not standings:
            ctk.CTkLabel(self.result_frame, text="Нет завершённых поединков",
                    text_color="#445566").pack(pady=30)
            return

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        for i, s in enumerate(standings):
            p = self.db.get_participant(s["pid"])
            if not p:
                continue
            place = s["place"] if "place" in s.keys() else i + 1
            medal = medals.get(place, f"#{place}")
            fg = "#1a3a1a" if place == 1 else "#1a2a3a"
            row = ctk.CTkFrame(self.result_frame, fg_color=fg, corner_radius=8)
            row.pack(fill="x", padx=10, pady=4)
            ctk.CTkLabel(row, text=f"{medal}  {p['name']}",
                    font=ctk.CTkFont(size=14, weight="bold" if place <= 3 else "normal"),
                    width=280, anchor="w").grid(row=0, column=0, padx=15, pady=10)
            ctk.CTkLabel(row, text=f"✅ {s['wins']} побед  ❌ {s['losses']} пораж.",
                    text_color="#8899aa", font=ctk.CTkFont(size=11)
                    ).grid(row=0, column=1, padx=20)
            ctk.CTkLabel(row, text=p["club"] if "club" in p.keys() and p["club"] else "—",
                    text_color="#5577aa", font=ctk.CTkFont(size=11)
                    ).grid(row=0, column=2, padx=10)

    # ────
    def _export_pdf(self):
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror("Ошибка", "Установите reportlab:\npip install reportlab")
            return
        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=f"protocol_{self.category['name']}_{self.hand}.pdf")
        if not filepath:
            return

        doc = SimpleDocTemplate(filepath, pagesize=A4,
                    leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                    topMargin=2 * cm, bottomMargin=2 * cm)
        styles = getSampleStyleSheet()
        story = []

        title_style = ParagraphStyle("Title", parent=styles["Title"],
                    fontName="Arial-Bold", fontSize=18, spaceAfter=6, alignment=1)
        story.append(Paragraph("ПРОТОКОЛ СОРЕВНОВАНИЙ ПО АРМРЕСТЛИНГУ", title_style))

        t = self.db.get_tournament(self.tournament_id)
        if t:
            info_style = ParagraphStyle("Info", parent=styles["Normal"],
                    fontName="Arial", fontSize=11, spaceAfter=4, alignment=1)
            story.append(Paragraph(
                f"{t['name']}  |  {t['date']}  |  {t['location'] or ''}", info_style))

        story.append(Paragraph(
            f"Весовая категория: {self.category['name']}  |  Рука: {self.hand}  |  Формат: До 2 поражений",
            ParagraphStyle("Cat", parent=styles["Normal"], fontName="Arial", fontSize=12, spaceAfter=12, alignment=1)))
        story.append(Spacer(1, 0.5 * cm))

        standings = self.engine.get_standings(self.category["id"], self.hand)
        if standings:
            story.append(Paragraph("ИТОГОВЫЕ РЕЗУЛЬТАТЫ",
                    ParagraphStyle("Section", parent=styles["Heading2"],
                    fontName="Arial-Bold", fontSize=13, spaceAfter=6)))
            data = [["Место", "Спортсмен", "Клуб", "Вес (кг)", "Победы", "Поражения"]]
            for i, s in enumerate(standings):
                p = self.db.get_participant(s["pid"])
                if not p:
                    continue
                place = s["place"] if "place" in s.keys() else i + 1
                medals_txt = {1: "1 (Золото)", 2: "2 (Серебро)", 3: "3 (Бронза)"}
                data.append([
                    medals_txt.get(place, str(place)),
                    p["name"], p["club"] or "—",
                    str(p["weight"]) if p["weight"] else "—",
                    str(s["wins"]), str(s["losses"])
                ])
            col_widths = [2.5 * cm, 6 * cm, 4.5 * cm, 2 * cm, 2 * cm, 2.5 * cm]
            t_table = Table(data, colWidths=col_widths, repeatRows=1)
            t_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a5c")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Arial-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Arial"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.HexColor("#f0f4f8"), colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("ROWHEIGHT", (0, 0), (-1, -1), 22),
                ("BACKGROUND", (0, 1), (0, 1), colors.HexColor("#ffd700")),
            ]))
            story.append(t_table)
            story.append(Spacer(1, 0.8 * cm))

        matches = self.db.get_matches(self.category["id"], self.hand)
        if matches:
            story.append(Paragraph("ВСЕ ПОЕДИНКИ",
                    ParagraphStyle("Section", parent=styles["Heading2"],
                    fontName="Arial-Bold", fontSize=13, spaceAfter=6)))
            m_data = [["Раунд", "Bracket", "Участник 1", "Участник 2", "Победитель"]]

            def pname(pid, m=None):
                if pid:
                    p = self.db.get_participant(pid)
                    return p["name"] if p else "?"
                if m is not None and m["is_bye"]:
                    return "BYE"
                return "—"

            for m in matches:
                m_data.append([
                    m["round_name"],
                    {"winners": "Winners", "losers": "Losers", "final": "Финал"}.get(
                    m["bracket"], ""),
                    pname(m["p1_id"], m), pname(m["p2_id"], m),
                    pname(m["winner_id"]) if m["winner_id"] else "—"
                ])
            col_widths2 = [2 * cm, 2.2 * cm, 4.5 * cm, 4.5 * cm, 4.5 * cm]
            m_table = Table(m_data, colWidths=col_widths2, repeatRows=1)
            m_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2a4a6c")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Arial-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Arial"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.HexColor("#f5f8fb"), colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
                ("ROWHEIGHT", (0, 0), (-1, -1), 18),
            ]))
            story.append(m_table)

        story.append(Spacer(1, 1 * cm))
        story.append(Paragraph(
            f"Дата создания протокола: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            ParagraphStyle("Footer", parent=styles["Normal"],
                    fontName="Arial", fontSize=8, textColor=colors.grey, alignment=2)))
        try:
            doc.build(story)
            messagebox.showinfo("Готово", f"PDF сохранён:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Ошибка PDF", str(e))


# ════
#  ОКНО ИТОГОВ ДВОЕБОРЬЯ (левая + правая рука → сумма очков)
# ════
class CombinedResultsWindow(ctk.CTkToplevel):
    """Показывает сводный зачёт двоеборья по одной весовой категории:
    место на правой руке + место на левой руке → очки → итоговое место.
    Полная расстановка мест: тот, кто выбыл раньше всех на обеих руках,
    автоматически оказывается в конце списка."""

    def __init__(self, master, db, tournament_id, category):
        super().__init__(master)
        self.withdraw()
        self.db = db
        self.tournament_id = tournament_id
        self.category = category
        tournament = db.get_tournament(tournament_id)
        bracket_system = tournament["bracket_system"] if tournament and "bracket_system" in tournament.keys() else "double"
        self.engine = SingleEliminationEngine(db) if bracket_system == "single" else DoubleEliminationEngine(db)
        self._rows_cache = []

        self.title(f"Итоги двоеборья — {category['name']}")
        self.geometry("980x680")
        self.minsize(760, 480)
        self.configure(fg_color="#0d1117")
        self.after(50, self.safe_init)

    def safe_init(self):
        try:
            self._build_ui()
            self._refresh()
            self.deiconify()
            self.update_idletasks()
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Ошибка", str(e))
            self.destroy()

    def _build_ui(self):
        top = ctk.CTkFrame(self, fg_color="#161b22", height=55)
        top.pack(fill="x", padx=0, pady=0)
        top.pack_propagate(False)

        ctk.CTkLabel(top, text=f"🏆  Итоги двоеборья  |  {self.category['name']}",
                    font=ctk.CTkFont(size=15, weight="bold")).pack(side="left", padx=20)

        ctk.CTkButton(top, text="📄 Протокол PDF", width=140, height=34,
                    fg_color="#1a4a2a", hover_color="#2a6a3a",
                    command=self._export_pdf).pack(side="right", padx=10, pady=10)
        ctk.CTkButton(top, text="🔄 Обновить", width=110, height=34,
                    command=self._refresh).pack(side="right", padx=5, pady=10)

        rules = ctk.CTkFrame(self, fg_color="#0d1f30", height=36)
        rules.pack(fill="x")
        rules.pack_propagate(False)
        ctk.CTkLabel(rules,
                    text="Очки: 1 место — 10 | 2 — 7 | 3 — 5 | 4 — 4 | 5 — 3 | 6 — 2 | 7 — 1 | 8 и ниже — 0",
                    text_color="#aabbcc", font=ctk.CTkFont(size=11)
                    ).pack(padx=20, pady=8, anchor="w")

        header = ctk.CTkFrame(self, fg_color="#1a2535")
        header.pack(fill="x", padx=10, pady=(10, 0))
        headers = ["Место", "Спортсмен", "Клуб", "Правая рука", "Левая рука", "Итого очков"]
        widths = [70, 240, 160, 160, 160, 110]
        for i, (h, w) in enumerate(zip(headers, widths)):
            ctk.CTkLabel(header, text=h, font=ctk.CTkFont(size=12, weight="bold"),
                    width=w, anchor="w").grid(row=0, column=i, padx=6, pady=8, sticky="w")

        self.result_scroll = ScrollableFrame(self, fg_color="#0d1117")
        self.result_scroll.pack(fill="both", expand=True, padx=10, pady=10)

    @staticmethod
    def _fmt_hand(place, points):
        if not place:
            return "— (0 очк.)"
        return f"{place} место ({points} очк.)"

    def _refresh(self):
        for w in self.result_scroll.winfo_children():
            w.destroy()
        rows = compute_dvoeborie_standings(self.db, self.engine, self.category)
        self._rows_cache = rows
        if not rows:
            ctk.CTkLabel(self.result_scroll,
                    text="Нет данных — сетки на руках ещё не сыграны",
                    text_color="#445566").pack(pady=30)
            return

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        PLACE_COLORS = {1: "#5a4610", 2: "#3d3f45", 3: "#4a2e15"}   # золото / серебро / бронза
        widths = [70, 240, 160, 160, 160, 110]
        for row in rows:
            place = row["place"]
            fg = PLACE_COLORS.get(place, "#1a2a3a")
            fr = ctk.CTkFrame(self.result_scroll, fg_color=fg, corner_radius=8)
            fr.pack(fill="x", padx=5, pady=3)
            medal = medals.get(place, f"#{place}")
            values = [
                medal,
                row["name"],
                row["club"],
                self._fmt_hand(row["right_place"], row["right_points"]),
                self._fmt_hand(row["left_place"], row["left_points"]),
                str(row["total_points"]),
            ]
            for i, (val, w) in enumerate(zip(values, widths)):
                ctk.CTkLabel(fr, text=str(val), width=w, anchor="w",
                    font=ctk.CTkFont(size=13, weight="bold" if place <= 3 else "normal")
                    ).grid(row=0, column=i, padx=6, pady=8, sticky="w")

    def _export_pdf(self):
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror("Ошибка", "Установите reportlab:\npip install reportlab")
            return
        rows = self._rows_cache or compute_dvoeborie_standings(self.db, self.engine, self.category)
        if not rows:
            messagebox.showwarning("Нет данных", "Нет результатов для экспорта.")
            return
        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=f"dvoeborie_{self.category['name']}.pdf")
        if not filepath:
            return

        doc = SimpleDocTemplate(filepath, pagesize=A4,
                    leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                    topMargin=2 * cm, bottomMargin=2 * cm)
        styles = getSampleStyleSheet()
        story = []

        title_style = ParagraphStyle("Title", parent=styles["Title"],
                    fontName="Arial-Bold", fontSize=18, spaceAfter=6, alignment=1)
        story.append(Paragraph("ИТОГИ ДВОЕБОРЬЯ", title_style))

        t = self.db.get_tournament(self.tournament_id)
        if t:
            info_style = ParagraphStyle("Info", parent=styles["Normal"],
                    fontName="Arial", fontSize=11, spaceAfter=4, alignment=1)
            story.append(Paragraph(
                f"{t['name']}  |  {t['date']}  |  {t['location'] or ''}", info_style))

        story.append(Paragraph(
            f"Весовая категория: {self.category['name']}",
            ParagraphStyle("Cat", parent=styles["Normal"], fontName="Arial", fontSize=12, spaceAfter=8, alignment=1)))
        story.append(Paragraph(
            "Очки: 1 место — 10, 2 — 7, 3 — 5, 4 — 4, 5 — 3, 6 — 2, 7 — 1, 8 место и ниже — 0.",
            ParagraphStyle("Rules", parent=styles["Normal"], fontName="Arial", fontSize=9,
                    textColor=colors.grey, spaceAfter=10, alignment=1)))
        story.append(Spacer(1, 0.3 * cm))

        data = [["Место", "Спортсмен", "Клуб", "Правая рука", "Левая рука", "Итого очков"]]
        for row in rows:
            def fmt(place, points):
                return f"{place} место ({points})" if place else "— (0)"
            data.append([
                str(row["place"]), row["name"], row["club"],
                fmt(row["right_place"], row["right_points"]),
                fmt(row["left_place"], row["left_points"]),
                str(row["total_points"]),
            ])
        col_widths = [1.8 * cm, 4.8 * cm, 3.2 * cm, 3.4 * cm, 3.4 * cm, 2.4 * cm]
        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a5c")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Arial-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Arial"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.HexColor("#f0f4f8"), colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("ROWHEIGHT", (0, 0), (-1, -1), 22),
            ("BACKGROUND", (0, 1), (0, 1), colors.HexColor("#ffd700")),
        ]))
        story.append(table)
        story.append(Spacer(1, 1 * cm))
        story.append(Paragraph(
            f"Дата создания протокола: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            ParagraphStyle("Footer", parent=styles["Normal"],
                    fontName="Arial", fontSize=8, textColor=colors.grey, alignment=2)))
        try:
            doc.build(story)
            messagebox.showinfo("Готово", f"PDF сохранён:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Ошибка PDF", str(e))


class AthleteCard(ctk.CTkFrame):
    def __init__(self, master, athlete, on_edit, on_delete, **kwargs):
        super().__init__(master, corner_radius=10, **kwargs)
        self.configure(fg_color=("#1e2a3a", "#1e2a3a"))
        a = athlete

        photo_label = ctk.CTkLabel(self, text="👤", font=("Arial", 28), width=50)
        if PIL_AVAILABLE and a["photo_path"] and Path(a["photo_path"]).exists():
            try:
                img = Image.open(a["photo_path"]).resize((50, 60))
                photo = ctk.CTkImage(img, size=(50, 60))
                photo_label = ctk.CTkLabel(self, image=photo, text="")
                photo_label._image = photo
            except Exception:
                pass
        photo_label.grid(row=0, column=0, rowspan=3, padx=(10, 5), pady=10)

        full_name = f"{a['last_name']} {a['first_name']}"
        ctk.CTkLabel(self, text=full_name, font=ctk.CTkFont(size=14, weight="bold"),
                    anchor="w").grid(row=0, column=1, sticky="w", padx=5, pady=(8, 0))

        gender_label = "Ж" if a["gender"] == "F" else "М"
        turning_age = datetime.now().year - int(a["birth_date"].split(".")[-1])
        natural_cat = compute_age_category(a["birth_date"], a["gender"])
        info = f"🎂 {a['birth_date']} ({turning_age} лет)   {gender_label}   🏛 {a['club'] or '—'}"
        ctk.CTkLabel(self, text=info, font=ctk.CTkFont(size=11),
                    text_color="#8899aa", anchor="w").grid(row=1, column=1, sticky="w", padx=5)

        cat_text = f"Категория: {natural_cat or '—'}"
        if a["rank"]:
            cat_text += f"   |   🥋 {a['rank']}"
        ctk.CTkLabel(self, text=cat_text, font=ctk.CTkFont(size=11), text_color="#5588bb",
                    anchor="w").grid(row=2, column=1, sticky="w", padx=5, pady=(0, 8))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=0, column=2, rowspan=3, padx=10, pady=10, sticky="e")
        ctk.CTkButton(btn_frame, text="✏️", width=36, height=32,
                    command=lambda: on_edit(a["id"])).pack(pady=2)
        ctk.CTkButton(btn_frame, text="🗑", width=36, height=32,
                    fg_color="#8b1a1a", hover_color="#a03030",
                    command=lambda: on_delete(a["id"])).pack(pady=2)
        self.columnconfigure(1, weight=1)


    # ════
    #  ОКНО «СПОРТСМЕНЫ» — общий реестр, не привязан к турниру
    # ════
class AthletesWindow(ctk.CTkToplevel):
    def __init__(self, master, db):
        super().__init__(master)
        self.withdraw()
        self.db = db
        self.title("👤 Спортсмены — общий реестр")
        self.geometry("820x640")
        self.minsize(600, 400)
        self.configure(fg_color="#0d1117")
        self.after(50, self.safe_init)

    def safe_init(self):
        self._build_ui()
        self._refresh_list()
        self.deiconify()

    def _build_ui(self):
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", padx=15, pady=15)

        ctk.CTkButton(ctrl, text="➕ Добавить спортсмена", width=190, height=38,
                    fg_color="#1a4a2a", hover_color="#2a6a3a",
                    command=lambda: self._add_athlete_dialog()).pack(side="left", padx=5)
        ctk.CTkButton(ctrl, text="🔄 Синхронизировать", width=170, height=38,
                    fg_color="#2a2a5a", hover_color="#3a3a7a",
                    command=self._sync_now).pack(side="left", padx=5)

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_list())
        ctk.CTkEntry(ctrl, textvariable=self.search_var, width=220,
                    placeholder_text="🔍 Поиск по имени/фамилии...").pack(side="left", padx=10)

        self.count_label = ctk.CTkLabel(ctrl, text="", text_color="#556677")
        self.count_label.pack(side="right", padx=10)

        self.list_frame = ScrollableFrame(self, fg_color="#0d1117")
        self.list_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

    def _refresh_list(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        athletes = self.db.search_athletes(self.search_var.get().strip())
        self.count_label.configure(text=f"Всего: {len(athletes)}")
        if not athletes:
            ctk.CTkLabel(self.list_frame, text="Нет спортсменов.",
                    text_color="#445566").pack(pady=20)
            return
        for a in athletes:
            card = AthleteCard(self.list_frame, a,
                    on_edit=self._add_athlete_dialog,
                    on_delete=self._delete_athlete)
            card.pack(fill="x", padx=5, pady=4)

    def _delete_athlete(self, aid):
        if not messagebox.askyesno("Удалить",
                    "Удалить спортсмена из реестра?\n"
                    "Из активных (незавершённых) турниров он будет удалён полностью.\n"
                    "В уже завершённых турнирах запись об участии сохранится."):
            return

        entered = simpledialog.askstring(
            "Подтверждение", "Введите пароль для удаления:", show="*", parent=self
        )
        if entered is None:
            return
        if entered != DELETE_ATHLETE_PASSWORD:
            messagebox.showerror("Неверный пароль", "Удаление отменено.")
            return

        self.db.delete_athlete(aid)
        self._refresh_list()

    def _sync_now(self):
        """Ручная отправка офлайн-очереди из окна реестра спортсменов —
        не привязана к конкретному турниру."""
        from sync.sync_manager import sync_manager

        pending = sync_manager.state.pending_count()
        if not pending:
            messagebox.showinfo("Синхронизация", "Очередь пуста — всё уже отправлено.")
            return

        done, remaining = sync_manager.flush_pending()
        if remaining:
            messagebox.showwarning(
                "Синхронизация",
                f"Отправлено {done} из {pending}.\n"
                f"Осталось {remaining} — похоже, связи всё ещё нет."
            )
        else:
            messagebox.showinfo("Синхронизация", f"Готово! Отправлено {done} операций.")


    def _add_athlete_dialog(self, edit_id=None):
        dlg = tk.Toplevel(self)
        dlg.title("Редактировать спортсмена" if edit_id else "Добавить спортсмена")
        dlg.geometry("660x660")
        dlg.minsize(480, 660)
        dlg.configure(bg="#161b22")

        fields = {}
        photo_path_var = ctk.StringVar()
        existing = self.db.get_athlete(edit_id) if edit_id else None

        def lbl_entry(parent, label, key, default="", row=0, placeholder=""):
            ctk.CTkLabel(parent, text=label, anchor="e", width=110).grid(
                row=row, column=0, padx=(15, 8), pady=8, sticky="e")
            var = ctk.StringVar(value=default)
            entry = ctk.CTkEntry(parent, textvariable=var, width=260, placeholder_text=placeholder)
            entry.grid(row=row, column=1, padx=(0, 15), pady=8, sticky="w")
            fields[key] = var
            return var

        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=10, pady=15)

        lbl_entry(form, "Имя*:", "first_name", existing["first_name"] if existing else "", row=0)
        lbl_entry(form, "Фамилия*:", "last_name", existing["last_name"] if existing else "", row=1)

        # ─── Дата рождения с автоматической маской дд.мм.гггг ───
        ctk.CTkLabel(form, text="Дата рожд.*:", anchor="e", width=110).grid(
            row=2, column=0, padx=(15, 8), pady=8, sticky="e")
        birth_date_var = ctk.StringVar(value=existing["birth_date"] if existing else "")
        birth_entry = ctk.CTkEntry(form, textvariable=birth_date_var, width=260,
                    placeholder_text="  .  .    ")
        birth_entry.grid(row=2, column=1, padx=(0, 15), pady=8, sticky="w")

        def format_birthdate(event=None):
            value = "".join(ch for ch in birth_entry.get() if ch.isdigit())[:8]

            result = ""
            if len(value) >= 1:
                result += value[:2]
            if len(value) > 2:
                result += "." + value[2:4]
            if len(value) > 4:
                result += "." + value[4:]

            cursor = len(result)

            birth_entry.delete(0, "end")
            birth_entry.insert(0, result)
            birth_entry.icursor(cursor)

        birth_entry.bind("<KeyRelease>", format_birthdate)

        # ─── Пол ───
        ctk.CTkLabel(form, text="Пол*:", anchor="e", width=110).grid(
            row=3, column=0, padx=(15, 8), pady=8, sticky="e")
        gender_display = {"M": "Мужской", "F": "Женский"}
        gender_reverse = {"Мужской": "M", "Женский": "F"}
        gender_var = ctk.StringVar(
            value=gender_display.get(existing["gender"], "Мужской") if existing else "Мужской")
        ctk.CTkOptionMenu(form, variable=gender_var,
                    values=["Мужской", "Женский"], width=260
                    ).grid(row=3, column=1, padx=(0, 15), pady=8, sticky="w")

        lbl_entry(form, "Клуб:", "club", existing["club"] or "" if existing else "", row=4)

        # ─── Звание (выпадающий список, обязательное) ───
        ctk.CTkLabel(form, text="Звание*:", anchor="e", width=110).grid(
            row=5, column=0, padx=(15, 8), pady=8, sticky="e")
        rank_var = ctk.StringVar(
            value=existing["rank"] if existing and existing["rank"] in RANKS else "Без звания")
        ctk.CTkOptionMenu(form, variable=rank_var, values=RANKS, width=260
                    ).grid(row=5, column=1, padx=(0, 15), pady=8, sticky="w")

        # ─── Фото (в отдельной строке, чтобы не наезжало на кнопку) ───
        ctk.CTkLabel(form, text="Фото:", anchor="e", width=110).grid(
            row=6, column=0, padx=(15, 8), pady=8, sticky="e")
        photo_row = ctk.CTkFrame(form, fg_color="transparent")
        photo_row.grid(row=6, column=1, padx=(0, 15), pady=8, sticky="w")

        photo_path_var.set(existing["photo_path"] or "" if existing else "")
        photo_lbl = ctk.CTkLabel(photo_row,
                    text=Path(photo_path_var.get()).name if photo_path_var.get() else "не выбрано",
                    text_color="#445566", width=140, anchor="w")
        photo_lbl.pack(side="left")

        def choose_photo():
            if not PIL_AVAILABLE:
                messagebox.showwarning("Нет PIL", "Установите Pillow:\npip install pillow")
                return
            p = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")])
            if p:
                dest = PHOTOS_DIR / Path(p).name
                import shutil
                shutil.copy2(p, dest)
                photo_path_var.set(str(dest))
                photo_lbl.configure(text=Path(p).name)

        ctk.CTkButton(photo_row, text="📷 Выбрать", width=100, height=28,
                    command=choose_photo).pack(side="left", padx=(10, 0))

        preview_label = ctk.CTkLabel(form, text="", text_color="#5588bb",
                    font=ctk.CTkFont(size=11), anchor="w", justify="left")
        preview_label.grid(row=7, column=0, columnspan=2, padx=15, pady=(12, 0), sticky="w")

        def update_preview(*_):
            bd = birth_date_var.get().strip()
            gender = gender_reverse[gender_var.get()]
            try:
                datetime.strptime(bd, "%d.%m.%Y")
                cat = compute_age_category(bd, gender)
                preview_label.configure(text=f"Возрастная категория: {cat or '—'}")
            except ValueError:
                preview_label.configure(text="")

        birth_date_var.trace_add("write", update_preview)
        gender_var.trace_add("write", update_preview)
        update_preview()

        def save():
            first_name = fields["first_name"].get().strip()
            last_name = fields["last_name"].get().strip()
            birth_date = birth_date_var.get().strip()
            if not first_name or not last_name:
                messagebox.showwarning("Ошибка", "Введите имя и фамилию.")
                return
            try:
                datetime.strptime(birth_date, "%d.%m.%Y")
            except ValueError:
                messagebox.showwarning("Ошибка", "Дата рождения в формате дд.мм.гггг (например, 25062002).")
                return
            gender = gender_reverse[gender_var.get()]
            club = fields["club"].get().strip()
            rank = rank_var.get()
            if edit_id:
                self.db.update_athlete(edit_id, first_name, last_name, birth_date,
                        gender, club, rank, photo_path_var.get())
            else:
                self.db.add_athlete(first_name, last_name, birth_date,
                        gender, club, rank, photo_path_var.get())
            print("Сохраняю спортсмена")
            dlg.destroy()
            self._refresh_list()

        btn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=15)
        ctk.CTkButton(btn_frame, text="💾 Сохранить", fg_color="#1a4a2a",
                    hover_color="#2a6a3a", height=40, command=save).pack(side="right", padx=5)
        ctk.CTkButton(btn_frame, text="Отмена", fg_color="#2a2a2a",
                    height=40, command=dlg.destroy).pack(side="right", padx=5)

        dlg.bind("<Return>", lambda e: save())

# ════
#  ГЛАВНОЕ ПРИЛОЖЕНИЕ
# ════
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.display_server = DisplayServer()
        self.display_server.start()
        self.current_tournament_id = None

        self.title("🦾 ArmWrestling Tournament Manager")
        self.geometry("1280x800")
        self.minsize(900, 600)
        self.configure(fg_color="#0d1117")

        # Открываем сразу на весь экран. 'zoomed' — стандартный способ на
        # Windows и большинстве Linux-WM; если он не поддерживается (бывает
        # на некоторых Linux/macOS сборках Tk) — пробуем -zoomed через
        # attributes, а если и это недоступно — просто растягиваем окно на
        # размер экрана вручную, чтобы приложение в любом случае открылось
        # на весь экран, а не в маленьком окне 1280x800.
        try:
            self.state("zoomed")
        except Exception:
            try:
                self.attributes("-zoomed", True)
            except Exception:
                self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")

        self._build_ui()
        self._refresh_status_badge()
        self._refresh_tournament_list()
        self._start_auto_sync()

    def _build_ui(self):
        self.sidebar = ctk.CTkFrame(self, width=240, corner_radius=0, fg_color="#161b22")
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        ctk.CTkLabel(self.sidebar,
                    text="🦾 ArmWrestling\nTournament",
                    font=ctk.CTkFont(size=16, weight="bold"),
                    text_color="#4a9eff").pack(pady=(20, 5), padx=15)
        ctk.CTkLabel(self.sidebar, text="Manager + Scanner",
                    font=ctk.CTkFont(size=11),
                    text_color="#445566").pack(pady=(0, 20))

        ctk.CTkButton(self.sidebar, text="➕ Новый турнир",
                    height=38, fg_color="#1a4a2a", hover_color="#2a6a3a",
                    command=self._new_tournament).pack(padx=15, pady=6, fill="x")
        
        ctk.CTkButton(self.sidebar, text="👤 Спортсмены", height=38,
                    fg_color="#1a2535", hover_color="#253545",
                    command=self._open_athletes_window).pack(padx=15, pady=(0, 6), fill="x")

        ctk.CTkLabel(self.sidebar, text="ТУРНИРЫ",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color="#445566").pack(padx=15, pady=(15, 5), anchor="w")

        self.tournament_scroll = ScrollableFrame(self.sidebar, fg_color="#161b22", height=400)
        self.tournament_scroll.pack(fill="x", padx=10, pady=5)

        ctk.CTkButton(self.sidebar, text="🗑 Удалить турнир",
                    height=34, fg_color="#3a1010", hover_color="#5a2020",
                    command=self._delete_tournament).pack(padx=15, pady=6, fill="x",
                    side="bottom")

        self.main = ctk.CTkFrame(self, fg_color="#0d1117", corner_radius=0)
        self.main.pack(side="right", fill="both", expand=True)

        self.header = ctk.CTkFrame(self.main, height=60, fg_color="#161b22", corner_radius=0)
        self.header.pack(fill="x")
        self.header.pack_propagate(False)
        self.title_label = ctk.CTkLabel(self.header,
                    text="Выберите или создайте турнир",
                    font=ctk.CTkFont(size=18, weight="bold"))
        self.title_label.pack(side="left", padx=25, pady=15)

        self.status_badge = ctk.CTkLabel(self.header, text="", text_color="#0d1117",
                    corner_radius=6, font=ctk.CTkFont(size=11, weight="bold"))
        self.status_badge.pack(side="left", padx=(0, 10), ipadx=8, ipady=3)

        self.finish_btn = ctk.CTkButton(self.header, text="🏁 Завершить турнир",
                    width=170, height=34,
                    fg_color="#4a3a1a", hover_color="#6a5a2a",
                    command=self._toggle_finish_tournament)
        self.finish_btn.pack(side="right", padx=20, pady=13)

        self.display_btn = ctk.CTkButton(self.header, text="📺 Табло",
                    width=110, height=34,
                    fg_color="#1a2535", hover_color="#253545",
                    command=self._open_display_board)
        self.display_btn.pack(side="right", padx=(0, 8), pady=13)

        self.notebook = ctk.CTkTabview(self.main, fg_color="#0d1117")
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self.notebook.add("⚖️ Категории")
        self.notebook.add("👥 Участники")
        self.notebook.add("🏆 Сетки")

        self._build_categories_tab()
        self._build_participants_tab()
        self._build_brackets_tab()

    def _build_categories_tab(self):
        tab = self.notebook.tab("⚖️ Категории")
        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=10)

        self.cat_search_var = ctk.StringVar()
        self.cat_search_var.trace_add("write", lambda *_: self._refresh_categories())

        ctk.CTkEntry(top, textvariable=self.cat_search_var,
                    placeholder_text="🔍 Поиск по названию, весу или возрасту",
                    height=38).pack(side="left", padx=(0, 10), fill="x", expand=True)

        ctk.CTkButton(top, text="🧙 Добавить категорию", width=190, height=38,
                    fg_color="#1a4a2a", hover_color="#2a6a3a",
                    command=self._open_category_wizard).pack(side="left")

        self.cat_list_frame = ScrollableFrame(tab, fg_color="#0d1117")
        self.cat_list_frame.pack(fill="both", expand=True, padx=10, pady=5)

    def _open_category_wizard(self):
        if not self.current_tournament_id:
            messagebox.showwarning("Нет турнира", "Сначала выберите турнир.")
            return
        if self._tournament_locked():
            return

        PLACEHOLDER = "— выберите —"

        win = ctk.CTkToplevel(self)
        win.title("Мастер добавления категории")
        win.geometry("420x300")
        win.transient(self)
        win.grab_set()

        age_keys = list(AGE_CATEGORY_RULES.keys())
        age_var = ctk.StringVar(value=PLACEHOLDER)
        weight_var = ctk.StringVar(value=PLACEHOLDER)
        hand_var = ctk.StringVar(value="Обе")

        ctk.CTkLabel(win, text="Возрастная категория:").pack(anchor="w", padx=20, pady=(20, 5))

        def refresh_weights(*_):
            age = age_var.get()
            if age == PLACEHOLDER:
                weight_menu.configure(values=[PLACEHOLDER], state="disabled")
                weight_var.set(PLACEHOLDER)
                return
            weights = AGE_CATEGORY_RULES[age]["weights"]
            labels = [str(w) for w in weights]
            weight_menu.configure(values=labels, state="normal")
            weight_var.set(labels[0])

        age_menu = ctk.CTkOptionMenu(win, variable=age_var,
                    values=[PLACEHOLDER] + age_keys, width=360, command=refresh_weights)
        age_menu.pack(padx=20)

        ctk.CTkLabel(win, text="Весовая категория:").pack(anchor="w", padx=20, pady=(15, 5))
        weight_menu = ctk.CTkOptionMenu(win, variable=weight_var,
                    values=[PLACEHOLDER], width=360, state="disabled")
        weight_menu.pack(padx=20)

        ctk.CTkLabel(win, text="Рука:").pack(anchor="w", padx=20, pady=(15, 5))
        ctk.CTkOptionMenu(win, variable=hand_var,
                    values=["Правая", "Левая", "Обе"], width=360).pack(padx=20)

        def confirm():
            age = age_var.get()
            w = weight_var.get()
            if age == PLACEHOLDER or w == PLACEHOLDER:
                messagebox.showwarning("Ошибка", "Выберите возрастную и весовую категорию.")
                return
            hand = hand_var.get()
            suffix = HAND_SUFFIX.get(hand, hand)

            if w == "Absolute":
                name = f"{age} {suffix}"
                self.db.add_category(self.current_tournament_id, name, "Absolute", hand, age)
            else:
                try:
                    weight_val = float(w.replace("+", ""))
                except ValueError:
                    weight_val = 0
                name = f"{age} {w}kg {suffix}"
                self.db.add_category(self.current_tournament_id, name, weight_val, hand, age)

            win.destroy()
            self._refresh_categories()

        ctk.CTkButton(win, text="➕ Добавить категорию", height=36,
                    fg_color="#1a4a2a", hover_color="#2a6a3a",
                    command=confirm).pack(padx=20, pady=25, fill="x")

    def _refresh_categories(self):
        for w in self.cat_list_frame.winfo_children():
            w.destroy()
        if not self.current_tournament_id:
            return
        cats = self.db.get_categories(self.current_tournament_id)
        query = self.cat_search_var.get().strip().lower()
        if query:
            cats = [c for c in cats
                    if query in c["name"].lower()
                    or query in str(c["max_weight"]).lower()
                    or query in c["hand"].lower()]
        if not cats:
            ctk.CTkLabel(self.cat_list_frame,
                    text="Ничего не найдено." if query else "Нет весовых категорий. Добавьте через мастер.",
                    text_color="#445566").pack(pady=20)
            return
        for cat in cats:
            fr = ctk.CTkFrame(self.cat_list_frame, fg_color="#1a2535", corner_radius=8)
            fr.pack(fill="x", padx=5, pady=4)
            count = len(self.db.get_participants(self.current_tournament_id, cat["id"]))
            text = f"⚖️  {cat['name']}  |  ✋ {cat['hand']}  |  👥 {count} участников"
            ctk.CTkLabel(fr, text=text,
                    font=ctk.CTkFont(size=13), anchor="w").pack(side="left", padx=15, pady=10)
            ctk.CTkButton(fr, text="🗑", width=36, height=30,
                    fg_color="#3a1010", hover_color="#5a2020",
                    command=lambda cid=cat["id"]: self._delete_category(cid)
                    ).pack(side="right", padx=10)

    def _delete_category(self, cid):
        if self._tournament_locked():
            return
        if messagebox.askyesno("Удалить", "Удалить категорию и всех её участников?"):
            self.db.delete_category(cid)
            self._refresh_categories()
            self._refresh_participants()

    def _build_participants_tab(self):
        tab = self.notebook.tab("👥 Участники")
        ctrl = ctk.CTkFrame(tab, fg_color="transparent")
        ctrl.pack(fill="x", padx=10, pady=10)

        ctk.CTkButton(ctrl, text="➕ Добавить участника", width=160, height=38,
                    fg_color="#1a4a2a", hover_color="#2a6a3a",
                    command=self._add_participant_dialog).pack(side="left", padx=5)

        # ═══ КНОПКА ПЕЧАТИ БЕЙДЖИКОВ ═══
        ctk.CTkButton(ctrl, text="🎫 Печать бейджиков", width=160, height=38,
                    fg_color="#4a3a1a", hover_color="#6a5a2a",
                    command=self._generate_badges_pdf).pack(side="left", padx=5)

        ctk.CTkLabel(ctrl, text="Фильтр:").pack(side="left", padx=(20, 5))
        self.filter_cat_var = ctk.StringVar(value="Все")
        self.filter_cat_menu = ctk.CTkOptionMenu(ctrl, variable=self.filter_cat_var,
                    values=["Все"],
                    command=lambda _: self._refresh_participants(),
                    width=160)
        self.filter_cat_menu.pack(side="left", padx=5)

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_participants())
        ctk.CTkEntry(ctrl, textvariable=self.search_var, width=200,
                    placeholder_text="🔍 Поиск по имени...").pack(side="left", padx=10)

        self.p_count_label = ctk.CTkLabel(ctrl, text="", text_color="#556677")
        self.p_count_label.pack(side="right", padx=15)

        self.participants_scroll = ScrollableFrame(tab, fg_color="#0d1117")
        self.participants_scroll.pack(fill="both", expand=True, padx=10, pady=5)

    # ════
    #  ГЕНЕРАЦИЯ PDF БЕЙДЖИКОВ
    # ════
    def _generate_badges_pdf(self):
        """Генерирует PDF с бейджиками всех участников текущего турнира."""
        if not self.current_tournament_id:
            messagebox.showwarning("Нет турнира", "Сначала выберите турнир.")
            return
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror("Ошибка", "Установите reportlab:\npip install reportlab")
            return

        participants = self.db.get_participants(self.current_tournament_id)
        if not participants:
            messagebox.showwarning("Нет участников", "Добавьте участников перед печатью бейджиков.")
            return

        # Собираем карту категорий
        cats = self.db.get_categories(self.current_tournament_id)
        categories_map = {c["id"]: c["name"] for c in cats}

        tournament = self.db.get_tournament(self.current_tournament_id)

        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=f"badges_{tournament['name']}.pdf"
        )
        if not filepath:
            return

        try:
            BadgeGenerator.generate(filepath, tournament, participants, categories_map)
            messagebox.showinfo(
                "Готово",
                f"Бейджики сохранены ({len(participants)} шт.):\n{filepath}\n\n"
                f"Формат штрихкода: {BARCODE_PREFIX}XXXX\n"
                f"Используйте USB-сканер для считывания."
            )
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось создать PDF:\n{str(e)}")

    def _sync_tournament(self):
        """Отправляет все накопленные данные в центральную БД."""
        if not self.current_tournament_id:
            messagebox.showwarning("Нет турнира", "Сначала выберите турнир.")
            return

        from sync.sync_manager import sync_manager

        pending = sync_manager.state.pending_count()
        if pending:
            done, remaining = sync_manager.flush_pending()
            if remaining:
                messagebox.showwarning(
                    "Синхронизация",
                    f"Отправлено {done} операций.\n"
                    f"Ещё {remaining} не прошло — повторите позже."
                )
            else:
                messagebox.showinfo(
                    "Готово",
                    f"Все {done} операций успешно отправлены."
                )
        else:
            messagebox.showinfo(
                "Синхронизация",
                "Нет операций для отправки — всё уже синхронизировано."
            )

    
    def _add_participant_dialog(self, edit_id=None):
        if not self.current_tournament_id:
            messagebox.showwarning("Нет турнира", "Сначала выберите турнир.")
            return
        if self._tournament_locked():
            return
        cats = self.db.get_categories(self.current_tournament_id)
        if not cats:
            messagebox.showwarning("Нет категорий", "Сначала добавьте весовые категории.")
            return

        dlg = tk.Toplevel(self)
        dlg.title("Редактировать участника" if edit_id else "Добавить участника")
        dlg.geometry("1000x1000")
        dlg.configure(bg="#161b22")

        dlg.transient (self)          # привязать к главному окну
        dlg.grab_set()               # сделать модальным
        dlg.attributes("-topmost", True)  # всегда поверх всех окон
        dlg.focus_force()     

        fields = {}
        existing = self.db.get_participant(edit_id) if edit_id else None
        _tournament = self.db.get_tournament(self.current_tournament_id)
        is_combined = bool(_tournament and _tournament["format_type"] == "combined")
        fields["club"] = ctk.StringVar(value=existing["club"] if existing and existing["club"] else "")
        photo_path_var = ctk.StringVar()

        # selected["athlete_id"] хранит id выбранного спортсмена из реестра athletes
        selected = {"athlete_id": existing["athlete_id"] if existing and existing["athlete_id"] else None}
        # state["eligible_cats"] хранит категории, доступные ИМЕННО этому спортсмену
        state = {"eligible_cats": []}

        def lbl_entry(parent, label, key, default="", row=0):
            ctk.CTkLabel(parent, text=label, anchor="e", width=110).grid(
                row=row, column=0, padx=(15, 8), pady=6, sticky="e")
            var = ctk.StringVar(value=default)
            entry = ctk.CTkEntry(parent, textvariable=var, width=240)
            entry.grid(row=row, column=1, padx=(0, 15), pady=6, sticky="w")
            fields[key] = var
            return var

        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=10, pady=10)

        # ── row 0: выбор спортсмена (вместо старого текстового поля "Имя") ──
        ctk.CTkLabel(form, text="Спортсмен*:", anchor="e", width=110).grid(
            row=0, column=0, padx=(15, 8), pady=6, sticky="e")

        athlete_display_var = ctk.StringVar()
        if selected["athlete_id"]:
            _a = self.db.get_athlete(selected["athlete_id"])
            if _a:
                athlete_display_var.set(f"{_a['first_name']} {_a['last_name']}")

        ctk.CTkEntry(form, textvariable=athlete_display_var, width=170,
                    state="readonly").grid(row=0, column=1, padx=(0, 0), pady=6, sticky="w")

        # ── row 1: вес на ЭТОМ турнире (как и было) ──
        lbl_entry(form, "Вес (кг):", "weight",
                  str(existing["weight"] or "") if existing else "", row=1)

        # Клуб больше не показываем в окне, но переменная нужна для сохранения
        # (заполняется автоматически из карточки спортсмена в choose_athlete)
        # ── row 2: категория — теперь чекбоксы, можно выбрать до 2 ──
        ctk.CTkLabel(form, text="Категории*:", anchor="e", width=110).grid(
            row=2, column=0, padx=(15, 8), pady=6, sticky="ne")
        cat_list_frame = ctk.CTkFrame(form, fg_color="transparent",width=250, height=1)
        cat_list_frame.grid(row=2, column=1, padx=(0, 15), pady=6, sticky="w")
        cat_vars = {}   # {category_id: BooleanVar}

        def on_check_toggle(cid):
            cat_age_map = {c["id"]: c["age_category"] for c in state["eligible_cats"]}
            already_ages = state.get("already_taken_ages", set())

            checked_ids = [c for c, v in cat_vars.items() if v.get()]
            non_abs_checked = [c for c in checked_ids
                                if not (cat_age_map.get(c) or "").startswith("Absolute")]
            ages_checked = [cat_age_map.get(c) for c in non_abs_checked]

            # общий счёт: то, что уже сохранено в других записях + то, что
            # отмечено прямо сейчас в этом окне
            total_non_abs = len(already_ages) + len(non_abs_checked)

            if total_non_abs > 2:
                cat_vars[cid].set(False)
                messagebox.showwarning("Ограничение",
                    "Спортсмен уже участвует максимум в 2 обычных категориях "
                    "(плюс, при желании, Абсолютная), учитывая его прошлые регистрации "
                    "в этом турнире.")
                validate_form()
                return

            all_ages = list(already_ages) + ages_checked
            if len(all_ages) != len(set(all_ages)):
                cat_vars[cid].set(False)
                messagebox.showwarning("Ограничение",
                    "Нельзя выбрать две категории из одной возрастной группы "
                    "(например, две Junior или две Senior) — в том числе с учётом "
                    "категорий, куда спортсмен уже записан ранее.")
                validate_form()
                return

            is_abs_cid = (cat_age_map.get(cid) or "").startswith("Absolute")
            if not is_abs_cid and selected["athlete_id"]:
                athlete = self.db.get_athlete(selected["athlete_id"])
                natural = compute_age_category(athlete["birth_date"], athlete["gender"])
                if natural and AGE_CATEGORY_RULES[natural]["level"] == 3 and total_non_abs > 1:
                    cat_vars[cid].set(False)
                    messagebox.showwarning("Ограничение",
                        "Спортсмен категории Senior может участвовать только "
                        "в одной обычной весовой категории.")
                    validate_form()
                    return

            validate_form()

        def update_categories(athlete):
            try:
                w = float(fields["weight"].get())
            except ValueError:
                w = 0
            eligible = self.db.get_eligible_categories(
            self.current_tournament_id, athlete["birth_date"], w, athlete["gender"])            
            state["eligible_cats"] = eligible

            # категории, в которых этот спортсмен УЖЕ зарегистрирован в этом турнире
            # (исключаем текущую запись, если мы её сейчас редактируем)
            all_parts = self.db.get_participants(self.current_tournament_id)
            all_cats = self.db.get_categories(self.current_tournament_id)
            cat_age_map_all = {c["id"]: c["age_category"] for c in all_cats}

            already_parts = [
                p for p in all_parts
                if p["athlete_id"] == athlete["id"] and p["id"] != edit_id
            ]
            already_taken_ids = {p["category_id"] for p in already_parts}
            # возрастные группы, которые спортсмен уже "занял" другими записями
            # (Абсолютная в этот лимит не входит — как и везде)
            already_taken_ages = {
                cat_age_map_all.get(p["category_id"])
                for p in already_parts
                if not (cat_age_map_all.get(p["category_id"]) or "").startswith("Absolute")
            }
            state["already_taken_ids"] = already_taken_ids
            state["already_taken_ages"] = already_taken_ages
            state["cat_age_map_all"] = cat_age_map_all

            for w in cat_list_frame.winfo_children():
                w.destroy()
            cat_vars.clear()

            if not eligible:
                ctk.CTkLabel(cat_list_frame, text="Нет доступных категорий",
                            text_color="#aa3333").pack(anchor="w")
                return

            existing_ids = [existing["category_id"]] if existing else []
            for c in eligible:
                is_taken = c["id"] in already_taken_ids
                var = ctk.BooleanVar(value=c["id"] in existing_ids)
                cb = ctk.CTkCheckBox(
                    cat_list_frame,
                    text=c["name"] + ("  ⚠ уже зарегистрирован" if is_taken else ""),
                    variable=var,
                    state="disabled" if is_taken else "normal",
                    command=lambda cid=c["id"]: on_check_toggle(cid))
                cb.pack(anchor="w", pady=2)
                cat_vars[c["id"]] = var
                if is_taken:
                    var.set(False)   # на всякий случай гарантированно снят
            validate_form()
        
        def on_weight_change(*_):
            if selected["athlete_id"]:
                a = self.db.get_athlete(selected["athlete_id"])
                update_categories(a)
            validate_form()

        fields["weight"].trace_add("write", on_weight_change)

        # ── row 3: рука (скрываем для двоеборья — участник и так борется обеими руками) ──
        hand_var = ctk.StringVar(value=existing["hand"] if existing else "Обе")
        if not is_combined:
            ctk.CTkLabel(form, text="Рука:", anchor="e", width=110).grid(
                row=3, column=0, padx=(15, 8), pady=6, sticky="e")
            ctk.CTkOptionMenu(form, variable=hand_var,
                        values=["Правая", "Левая", "Обе"], width=240
                        ).grid(row=3, column=1, padx=(0, 15), pady=6, sticky="w")

        # ── row 4: фото (как и было) ──
        ctk.CTkLabel(form, text="Фото:", anchor="e", width=110).grid(
            row=4, column=0, padx=(15, 8), pady=6, sticky="e")
        photo_path_var.set(existing["photo_path"] or "" if existing else "")
        photo_lbl = ctk.CTkLabel(form,
                    text=Path(photo_path_var.get()).name if photo_path_var.get() else "не выбрано",
                    text_color="#445566", width=160, anchor="w")
        photo_lbl.grid(row=4, column=1, padx=(0, 0), pady=6, sticky="w")

        def choose_photo():
            if not PIL_AVAILABLE:
                messagebox.showwarning("Нет PIL", "Установите Pillow:\npip install pillow")
                return
            p = filedialog.askopenfilename(
                filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")])
            if p:
                dest = PHOTOS_DIR / Path(p).name
                import shutil
                shutil.copy2(p, dest)
                photo_path_var.set(str(dest))
                photo_lbl.configure(text=Path(p).name)

        ctk.CTkButton(form, text="📷 Выбрать", width=80, height=28,
                    command=choose_photo).grid(row=4, column=1, padx=(170, 0), pady=6,
                    sticky="w")

        # ── кнопка выбора спортсмена (ставим ПОСЛЕ объявления всех полей формы,
        #    чтобы choose_athlete/update_categories видели fields["club"] и т.д.) ──
        def choose_athlete():
            picker = tk.Toplevel(dlg)
            picker.title("Выбрать спортсмена")
            picker.geometry("420x480")
            picker.transient(dlg)
            picker.grab_set()

            search_var = ctk.StringVar()
            ctk.CTkEntry(picker, textvariable=search_var, width=380,
                        placeholder_text="🔍 Поиск по имени/фамилии...").pack(padx=10, pady=10)

            results_frame = ScrollableFrame(picker, fg_color="#0d1117")
            results_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

            def refresh():
                for w in results_frame.winfo_children():
                    w.destroy()
                found = self.db.search_athletes(search_var.get().strip())
                if not found:
                    ctk.CTkLabel(results_frame, text="Нет спортсменов. Добавьте через «Спортсмены».",
                                text_color="#445566").pack(pady=20)
                    return
                for a in found:
                    def pick(a=a):
                        selected["athlete_id"] = a["id"]
                        athlete_display_var.set(f"{a['first_name']} {a['last_name']}")
                        if not fields["club"].get():
                            fields["club"].set(a["club"] or "")
                        if not photo_path_var.get() and a["photo_path"]:
                            photo_path_var.set(a["photo_path"])
                            photo_lbl.configure(text=Path(a["photo_path"]).name)
                        update_categories(a)
                        validate_form()
                        picker.destroy()
                    ctk.CTkButton(results_frame,
                                text=f"{a['first_name']} {a['last_name']} ({a['club'] or '—'})",
                                anchor="w", fg_color="#1a1f28", hover_color="#2a2f38",
                                command=pick).pack(fill="x", padx=5, pady=3)

            search_var.trace_add("write", lambda *_: refresh())
            refresh()

        ctk.CTkButton(form, text="🔍 Выбрать", width=80, height=28,
                    command=choose_athlete).grid(row=0, column=1, padx=(180, 0), pady=6, sticky="w")

        # если это редактирование существующего участника — сразу подтянуть
        # допустимые категории для уже привязанного спортсмена
        # Показываем штрихкод если редактируем
        if existing:
            barcode_val = get_barcode_value(existing["id"])
            ctk.CTkLabel(form, text="Штрихкод:", anchor="e", width=110).grid(
                row=7, column=0, padx=(15, 8), pady=6, sticky="e")
            ctk.CTkLabel(form, text=barcode_val, font=ctk.CTkFont(size=13, weight="bold"),
                    text_color="#ffaa00").grid(row=7, column=1, padx=(0, 15), pady=6, sticky="w")

        def validate_form(*_):
            ok = (
                selected["athlete_id"] is not None
                and fields["weight"].get().strip() != ""
                and any(v.get() for v in cat_vars.values())
            )
            save_btn.configure(state="normal" if ok else "disabled")

        def save():
            if not selected["athlete_id"]:
                messagebox.showwarning("Ошибка", "Выберите спортсмена из реестра.")
                return
            athlete = self.db.get_athlete(selected["athlete_id"])
            name = f"{athlete['first_name']} {athlete['last_name']}"
            try:
                weight = round(float(fields["weight"].get()), 3) if fields["weight"].get() else 0
            except ValueError:
                weight = 0
            club = fields["club"].get().strip()
            if not state["eligible_cats"]:
                messagebox.showwarning("Ошибка",
                    "Для этого спортсмена нет доступных категорий в этом турнире.")
                return
            selected_cat_ids = [cid for cid, v in cat_vars.items() if v.get()]
            if not selected_cat_ids:
                messagebox.showwarning("Ошибка", "Выберите хотя бы одну категорию.")
                return

            cat_age_map = {c["id"]: c["age_category"] for c in state["eligible_cats"]}
            already_ages = state.get("already_taken_ages", set())
            non_abs_selected = [c for c in selected_cat_ids
                                if not (cat_age_map.get(c) or "").startswith("Absolute")]
            ages_selected = [cat_age_map.get(c) for c in non_abs_selected]

            total_non_abs = len(already_ages) + len(non_abs_selected)
            if total_non_abs > 2:
                messagebox.showwarning("Ошибка",
                    "Максимум 2 обычные категории (плюс Абсолютная), учитывая "
                    "уже сохранённые ранее регистрации этого спортсмена в этом турнире.")
                return

            all_ages = list(already_ages) + ages_selected
            if len(all_ages) != len(set(all_ages)):
                messagebox.showwarning("Ошибка",
                    "Нельзя выбрать две категории из одной возрастной группы "
                    "(в том числе с учётом уже сохранённых ранее регистраций).")
                return

            natural = compute_age_category(athlete["birth_date"], athlete["gender"])
            if natural and AGE_CATEGORY_RULES[natural]["level"] == 3 and total_non_abs > 1:
                messagebox.showwarning("Ошибка",
                    "Спортсмен категории Senior может участвовать только "
                    "в одной обычной весовой категории.")
                return
            
            # Поле "Возраст. кат." убрано из окна — считаем автоматически по дате рождения
            computed_age_cat = compute_age_category(athlete["birth_date"], athlete["gender"]) or "Senior"
            if edit_id:
                self.db.update_participant(edit_id, name, weight, club, selected_cat_ids[0],
                    hand_var.get(), photo_path_var.get(), computed_age_cat,
                    athlete_id=selected["athlete_id"])
            else:
                for cid in selected_cat_ids:
                    self.db.add_participant(self.current_tournament_id, name, weight, club,
                        cid, hand_var.get(), photo_path_var.get(), computed_age_cat,
                        athlete_id=selected["athlete_id"])

            dlg.destroy()
            self._refresh_participants()

        btn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=10)
        save_btn = ctk.CTkButton(btn_frame, text="💾 Сохранить", fg_color="#1a4a2a",
                    hover_color="#2a6a3a", height=40, command=save, state="disabled")
        save_btn.pack(side="right", padx=5)
        ctk.CTkButton(btn_frame, text="Отмена", fg_color="#2a2a2a",
                    height=40, command=dlg.destroy).pack(side="right", padx=5)
        
        if selected["athlete_id"]:
            _existing_athlete = self.db.get_athlete(selected["athlete_id"])
            if _existing_athlete:
                update_categories(_existing_athlete)
            validate_form()




    def _refresh_participants(self):
        for w in self.participants_scroll.winfo_children():
            w.destroy()
        if not self.current_tournament_id:
            return
        cats = self.db.get_categories(self.current_tournament_id)
        cat_names = ["Все"] + [c["name"] for c in cats]
        self.filter_cat_menu.configure(values=cat_names)

        selected_cat = self.filter_cat_var.get()
        cat_id = None
        if selected_cat != "Все":
            for c in cats:
                if c["name"] == selected_cat:
                    cat_id = c["id"]

        query = self.search_var.get().lower().strip()
        participants = self.db.get_participants(self.current_tournament_id, cat_id)
        if query:
            participants = [p for p in participants if query in p["name"].lower()]

        self.p_count_label.configure(text=f"Всего: {len(participants)}")
        if not participants:
            ctk.CTkLabel(self.participants_scroll,
                    text="Нет участников." if not query else "Не найдено.",
                    text_color="#445566").pack(pady=20)
            return

        # Группируем регистрации одного и того же спортсмена (по athlete_id),
        # чтобы участник в 2 категориях показывался ОДНОЙ карточкой, а не двумя.
        groups = {}
        order = []
        for p in participants:
            has_athlete_id = "athlete_id" in p.keys() and p["athlete_id"]
            key = f"athlete:{p['athlete_id']}" if has_athlete_id else f"solo:{p['id']}"
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(p)

        for key in order:
            card = ParticipantGroupCard(self.participants_scroll, groups[key],
                    on_edit=self._add_participant_dialog,
                    on_delete=self._delete_participant)
            card.pack(fill="x", padx=5, pady=4)
    def _delete_participant(self, pid):
        if self._tournament_locked():
            return
        if messagebox.askyesno("Удалить", "Удалить участника?"):
            self.db.delete_participant(pid)
            self._refresh_participants()

    def _build_brackets_tab(self):
        tab = self.notebook.tab("🏆 Сетки")

        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(20, 0))
        ctk.CTkLabel(top,
                    text="Выберите категорию и руку для открытия сетки:",
                    font=ctk.CTkFont(size=13), text_color="#778899"
                    ).pack(side="left")
        # ═══ КНОПКА СИНХРОНИЗАЦИИ ═══
        ctk.CTkButton(top, text="🔄 Синхронизация", width=190, height=38,
                    fg_color="#1a3a5a", hover_color="#2a5a7a",
                    command=self._sync_tournament).pack(side="right")

        self.bracket_list = ScrollableFrame(tab, fg_color="#0d1117")
        self.bracket_list.pack(fill="both", expand=True, padx=20, pady=10)

    def _refresh_brackets_tab(self):
        for w in self.bracket_list.winfo_children():
            w.destroy()
        if not self.current_tournament_id:
            return
        cats = self.db.get_categories(self.current_tournament_id)
        if not cats:
            ctk.CTkLabel(self.bracket_list,
                    text="Нет категорий.", text_color="#445566").pack(pady=20)
            return

        tournament = self.db.get_tournament(self.current_tournament_id)
        format_type = tournament["format_type"] if tournament and "format_type" in tournament.keys() else "separate"

        for cat in cats:
            both_hands = cat["hand"] == "Обе"
            hands = ["Правая", "Левая"] if both_hands else [cat["hand"]]
            count = len(self.db.get_participants(self.current_tournament_id, cat["id"]))

            # ── Одна карточка на категорию (а не по одной строке на руку) ──
            card = ctk.CTkFrame(self.bracket_list, fg_color="#151c2c", corner_radius=14,
                border_width=1, border_color="#26314a")
            card.pack(fill="x", padx=5, pady=8)

            head = ctk.CTkFrame(card, fg_color="transparent")
            head.pack(fill="x", padx=18, pady=(14, 8))

            head_icon = "🤝" if both_hands else ("🤜" if cat["hand"] == "Правая" else "🤛")
            ctk.CTkLabel(head, text=f"{head_icon}  {cat['name']}",
                    font=ctk.CTkFont(size=15, weight="bold"), anchor="w"
                    ).pack(side="left")
            ctk.CTkLabel(head, text=f"👥 {count} уч.",
                    text_color="#5588aa", font=ctk.CTkFont(size=12)
                    ).pack(side="left", padx=14)
            if both_hands:
                ctk.CTkLabel(head, text="ОБЕ РУКИ", text_color="#0d1117",
                        fg_color="#4dccff", corner_radius=6,
                        font=ctk.CTkFont(size=10, weight="bold")
                        ).pack(side="left", padx=6, ipadx=8, ipady=2)

            # ── Панели: одна колонка на руку (+ колонка "Двоеборье", если нужно) ──
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=(0, 16))

            for hand in hands:
                matches = self.db.get_matches(cat["id"], hand)
                done = sum(1 for m in matches if m["status"] == "done")
                total = len([m for m in matches if m["status"] != "bye"])
                status_text = f"✅ {done}/{total} поединков" if total else "Сетка не создана"

                hfr = ctk.CTkFrame(row, fg_color="#1a2535", corner_radius=10)
                hfr.pack(side="left", fill="both", expand=True, padx=4)

                hicon = "🤜" if hand == "Правая" else "🤛"
                ctk.CTkLabel(hfr, text=f"{hicon}  {hand} рука",
                        font=ctk.CTkFont(size=13, weight="bold"), anchor="w"
                        ).pack(anchor="w", padx=14, pady=(12, 2))
                ctk.CTkLabel(hfr, text=status_text, text_color="#4488aa",
                        font=ctk.CTkFont(size=11), anchor="w"
                        ).pack(anchor="w", padx=14, pady=(0, 10))
                ctk.CTkButton(hfr, text="🔍 Открыть сетку", height=32,
                        command=lambda c=cat, h=hand: BracketWindow(
                        self, self.db, self.current_tournament_id, c, h)
                        ).pack(fill="x", padx=14, pady=(0, 14))

            # ── Двоеборье: сводный зачёт по обеим рукам для этой категории ──
            if format_type == "combined" and both_hands:
                dv_fr = ctk.CTkFrame(row, fg_color="#2a2410", corner_radius=10,
                        border_width=1, border_color="#7a6a20")
                dv_fr.pack(side="left", fill="both", expand=True, padx=4)
                ctk.CTkLabel(dv_fr, text="🏆  Двоеборье",
                        font=ctk.CTkFont(size=13, weight="bold"),
                        text_color="#ffd166", anchor="w"
                        ).pack(anchor="w", padx=14, pady=(12, 2))
                ctk.CTkLabel(dv_fr, text="Сумма очков за обе руки",
                        text_color="#c9b064", font=ctk.CTkFont(size=11), anchor="w"
                        ).pack(anchor="w", padx=14, pady=(0, 10))
                ctk.CTkButton(dv_fr, text="📊 Итоги двоеборья", height=32,
                        fg_color="#7a6a20", hover_color="#9a8a30",
                        command=lambda c=cat: CombinedResultsWindow(
                        self, self.db, self.current_tournament_id, c)
                        ).pack(fill="x", padx=14, pady=(0, 14))

    def _refresh_tournament_list(self):
        for w in self.tournament_scroll.winfo_children():
            w.destroy()
        tournaments = self.db.get_tournaments()
        if not tournaments:
            ctk.CTkLabel(self.tournament_scroll,
                    text="Нет турниров.\nСоздайте первый!",
                    text_color="#445566",
                    font=ctk.CTkFont(size=11),
                    justify="center").pack(pady=20, padx=10)
            return
        for t in tournaments:
            fr = ctk.CTkFrame(self.tournament_scroll, corner_radius=8,
                    fg_color="#1a2535" if t["id"] != self.current_tournament_id else "#1a3a5a")
            fr.pack(fill="x", padx=5, pady=3)
            ctk.CTkButton(fr,
                    text=f"🏅 {t['name']}\n{t['date']}",
                    fg_color="transparent", hover_color="#253545",
                    font=ctk.CTkFont(size=11), anchor="w",
                    height=48,
                    command=lambda tid=t["id"]: self._select_tournament(tid)
                    ).pack(fill="x", padx=2, pady=2)

    def _select_tournament(self, tid):
        self.current_tournament_id = tid
        t = self.db.get_tournament(tid)
        self.title_label.configure(
            text=f"🏆  {t['name']}  |  {t['date']}  |  {t['location'] or ''}")
        self._refresh_status_badge(t)
        self._refresh_tournament_list()
        self._refresh_categories()
        self._refresh_participants()
        self._refresh_brackets_tab()

    def _refresh_status_badge(self, tournament=None):
        """Обновляет бейджик статуса и текст кнопки завершения/возобновления."""
        if not self.current_tournament_id:
            self.status_badge.configure(text="")
            self.finish_btn.configure(text="🏁 Завершить турнир",
                    fg_color="#4a3a1a", hover_color="#6a5a2a", state="disabled")
            return
        t = tournament or self.db.get_tournament(self.current_tournament_id)
        finished = bool(t and "status" in t.keys() and t["status"] == "finished")
        if finished:
            self.status_badge.configure(text="ЗАВЕРШЁН", fg_color="#ff6666")
            self.finish_btn.configure(text="↩️ Возобновить турнир",
                    fg_color="#1a3a5a", hover_color="#2a5a7a", state="normal")
        else:
            self.status_badge.configure(text="АКТИВЕН", fg_color="#4dff88")
            self.finish_btn.configure(text="🏁 Завершить турнир",
                    fg_color="#4a3a1a", hover_color="#6a5a2a", state="normal")

    def _toggle_finish_tournament(self):
        if not self.current_tournament_id:
            return
        if self.db.is_tournament_finished(self.current_tournament_id):
            if messagebox.askyesno("Возобновить турнир",
                        "Возобновить турнир?\n"
                        "Снова станут доступны добавление/удаление участников, "
                        "категорий и создание сеток."):
                self.db.reopen_tournament(self.current_tournament_id)
                from sync.sync_manager import sync_manager
                sync_manager.update_tournament_status(self.current_tournament_id, "in_progress")
        else:
            if messagebox.askyesno("Завершить турнир",
                        "Завершить турнир?\n"
                        "После этого нельзя будет добавлять/удалять участников, "
                        "категории и создавать/сбрасывать сетки — только просмотр.\n"
                        "Завершённый турнир можно будет возобновить в любой момент."):
                self.db.finish_tournament(self.current_tournament_id)
                from sync.sync_manager import sync_manager
                sync_manager.update_tournament_status(self.current_tournament_id, "completed")
        self._select_tournament(self.current_tournament_id)

    def _tournament_locked(self, show_warning=True):
        """True, если текущий турнир завершён и изменения запрещены."""
        if not self.current_tournament_id:
            return False
        locked = self.db.is_tournament_finished(self.current_tournament_id)
        if locked and show_warning:
            messagebox.showwarning("Турнир завершён",
                    "Турнир завершён — изменения недоступны.\n"
                    "Можно только просматривать участников и сетки.\n"
                    "Чтобы снова редактировать, нажмите «Возобновить турнир».")
        return locked
    
    def _open_athletes_window(self):
        if hasattr(self, "_athletes_window") and self._athletes_window.winfo_exists():
            self._athletes_window.focus()
            return
        self._athletes_window = AthletesWindow(self, self.db)

    def _new_tournament(self):
        dlg = tk.Toplevel(self)
        dlg.title("Новый турнир")
        dlg.geometry("500x800")
        dlg.minsize(420, 500)
        dlg.configure(bg="#161b22")
        dlg.resizable(True, True)

        dlg.update_idletasks()
        x = self.winfo_x() + self.winfo_width() // 2 - 230
        y = self.winfo_y() + self.winfo_height() // 2 - 190
        dlg.geometry(f"500x800+{x}+{y}")

        ctk.CTkLabel(dlg, text="🏆  Создать турнир",
                    font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(25, 15))

        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="x", padx=35)

        name_var = ctk.StringVar()
        date_var = ctk.StringVar(value=datetime.now().strftime("%d.%m.%Y"))
        loc_var = ctk.StringVar()

        fields_cfg = [
            ("Название *", name_var, "Чемпионат города по армрестлингу"),
            ("Дата *", date_var, "дд.мм.гггг"),
            ("Место проведения", loc_var, "Спортивный зал, г. Атырау"),
        ]
        entries = {}
        for label, var, ph in fields_cfg:
            ctk.CTkLabel(form, text=label, anchor="w",
                    font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(10, 2))
            e = ctk.CTkEntry(form, textvariable=var, placeholder_text=ph,
                    height=38, font=ctk.CTkFont(size=13))
            e.pack(fill="x", pady=(0, 2))
            entries[label] = e

        ctk.CTkLabel(form,
                    text="* После создания турнира добавьте весовые категории и участников",
                    text_color="#445566", font=ctk.CTkFont(size=10),
                    wraplength=380, justify="left").pack(anchor="w", pady=(8, 0))
        
        tol_var = ctk.StringVar(value="0.100")
        ctk.CTkLabel(form, text="Допуск по весу (кг)", anchor="w",
                    font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(14, 2))
        tol_row = ctk.CTkFrame(form, fg_color="transparent")
        tol_row.pack(fill="x")
        tol_entry = ctk.CTkEntry(tol_row, textvariable=tol_var, width=120, height=38)
        tol_entry.pack(side="left")
        tol_hint = ctk.CTkLabel(tol_row, text="= 100 г", text_color="#445566")
        tol_hint.pack(side="left", padx=(10, 0))

        def update_tol_hint(*_):
            try:
                grams = round(float(tol_var.get()) * 1000)
                tol_hint.configure(text=f"= {grams} г")
            except ValueError:
                tol_hint.configure(text="")
        tol_var.trace_add("write", update_tol_hint)
        ctk.CTkLabel(form, text="Формат соревнований", anchor="w",
                    font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(14, 2))
        format_var = ctk.StringVar(value="На отдельных руках")
        ctk.CTkOptionMenu(form, variable=format_var,
                    values=["На отдельных руках", "Двоеборье"],
                    width=380).pack(fill="x")

        ctk.CTkLabel(form, text="Система сетки", anchor="w",
                    font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(14, 2))
        system_var = ctk.StringVar(value="Double elimination (до двух поражений)")
        ctk.CTkOptionMenu(form, variable=system_var,
                    values=["Double elimination (до двух поражений)",
                            "Single elimination (до одного поражения)"],
                    width=380).pack(fill="x")

        def save():
            if not name_var.get().strip():
                messagebox.showwarning("Ошибка", "Введите название турнира.")
                entries["Название *"].focus()
                return
            if not date_var.get().strip():
                messagebox.showwarning("Ошибка", "Введите дату турнира.")
                entries["Дата *"].focus()
                return
            try:
                tolerance = float(tol_var.get()) if tol_var.get().strip() else 0
            except ValueError:
                tolerance = 0
            bracket_system = "single" if "Single" in system_var.get() else "double"
            format_type = "combined" if format_var.get() == "Двоеборье" else "separate"
            tid = self.db.create_tournament(name_var.get().strip(),
                    date_var.get().strip(),
                    loc_var.get().strip(),
                    tolerance,
                    bracket_system,
                    format_type)
            dlg.destroy()
            self._refresh_tournament_list()
            self._select_tournament(tid)

        btn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_frame.pack(fill="x", padx=35, pady=20, side="bottom")

        ctk.CTkButton(btn_frame, text="Отмена", height=42, width=120,
                    fg_color="#2a2a3a", hover_color="#3a3a4a",
                    command=dlg.destroy).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_frame, text="✅  Создать турнир", height=42,
                    fg_color="#1a5a2a", hover_color="#57a667",
                    font=ctk.CTkFont(size=13, weight="bold"),
                    command=save).pack(side="right")

        dlg.bind("<Return>", lambda e: save())

    def _open_display_board(self):
        """Открывает табло очереди поединков (страница self.display_server,
        см. класс DisplayServer) в браузере по умолчанию. Также показывает
        LAN-адрес, чтобы можно было открыть табло на другом экране/проекторе
        в той же сети (WiFi зала)."""
        import socket
        lan_ip = "localhost"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                lan_ip = s.getsockname()[0]
            finally:
                s.close()
        except OSError:
            pass

        local_url = "http://localhost:5000"
        webbrowser.open(local_url)

        if lan_ip != "localhost":
            messagebox.showinfo(
                "Табло",
                f"Табло открыто в браузере.\n\n"
                f"Чтобы показать его на другом устройстве (проектор, экран, "
                f"телефон) в этой же WiFi-сети, откройте:\nhttp://{lan_ip}:5000",
            )

    def _delete_tournament(self):
        if not self.current_tournament_id:
            return
        t = self.db.get_tournament(self.current_tournament_id)
        if messagebox.askyesno("Удалить",
                    f"Удалить турнир «{t['name']}» и все данные?"):
            self.db.delete_tournament(self.current_tournament_id)
            self.current_tournament_id = None
            self.title_label.configure(text="Выберите или создайте турнир")
            self._refresh_tournament_list()
            self._refresh_categories()
            self._refresh_participants()
            self._refresh_brackets_tab()

    def on_close(self):
        if messagebox.askyesno("Выход", "Закрыть программу?"):
            self.db.close()
            self.destroy()

    def _start_auto_sync(self):
        """Запускает периодическую проверку подключения и авто-flush очереди."""
        self.after(10000, self._auto_sync_tick)

    def _auto_sync_tick(self):
        from sync.sync_manager import sync_manager
        if sync_manager.state.pending_count() > 0:
            result = sync_manager.try_auto_flush()
            if result:
                succeeded, remaining = result
                if succeeded > 0:
                    print(f"[auto-sync] отправлено {succeeded}, осталось {remaining}")
                    self._refresh_status_badge()
                    if remaining == 0:
                        self._show_sync_toast("Все данные синхронизированы")
        self.after(10000, self._auto_sync_tick)

    def _show_sync_toast(self, message):
        import tkinter as tk
        toast = tk.Toplevel(self)
        toast.overrideredirect(True)
        toast.configure(bg="#1a3a5a")
        x = self.winfo_x() + self.winfo_width() // 2 - 150
        y = self.winfo_y() + self.winfo_height() - 60
        toast.geometry(f"300x36+{x}+{y}")
        tk.Label(toast, text=message, bg="#1a3a5a", fg="#e0e0e0",
                 font=("Segoe UI", 11)).pack(expand=True)
        toast.after(3000, toast.destroy)


# ════
#  ЗАПУСК
# ════
if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
