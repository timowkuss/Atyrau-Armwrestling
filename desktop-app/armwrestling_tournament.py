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
import io
import json
import tempfile
import re
from datetime import datetime
from pathlib import Path
import random
from collections import OrderedDict
from flask import Flask
from threading import Thread
import webbrowser

from paths import (app_dir, backups_dir, data_path, db_path, env_file,
                   photos_dir, resource_path, sync_state_db_path, is_frozen)

# ─── .env рядом со скриптом/exe — сюда судья/организатор прописывает
# CLOUDINARY_CLOUD_NAME и CLOUDINARY_UPLOAD_PRESET (см. sync/cloudinary_client.py).
# ДОЛЖНО стоять раньше импорта sync.cloudinary_client ниже — тот читает
# os.environ на уровне модуля, при самом импорте.
try:
    from dotenv import load_dotenv
    # Грузим .env из папки самого скрипта, а НЕ из текущего каталога: если
    # приложение запущено ярлыком/из другого места, CWD может не совпадать
    # с desktop-app/, и иначе .env (в т.ч. DESKTOP_SYNC_TOKEN и Cloudinary)
    # молча не подхватится — весь sync начнёт падать с 401.
    load_dotenv(env_file())
except ImportError:
    pass  # python-dotenv не установлен — просто не подхватываем .env,
          # переменные окружения всё ещё можно задать вручную в системе

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

# Центральная тема/палитра — весь внешний вид приложения (цвета, шрифты,
# отступы, переиспользуемые компоненты). Бизнес-логики в ней нет.
from ui_theme import (theme, BG, PANEL, PANEL_LIGHT, CARD, CARD_ALT, INPUT_BG,
                      BORDER, CARD_BORDER, SELECTED, TEXT, TEXT_DIM, TEXT_FAINT,
                      TEXT_BRIGHT, ACCENT, ACCENT_HOVER, ACCENT_DIM, SUCCESS,
                      SUCCESS_HOVER, WARNING, WARNING_HOVER, DANGER, DANGER_HOVER,
                       OK, ERR, WARN, GOLD, DROPDOWN_BG, DROPDOWN_HOVER,
                       INFO_HOVER, OptionMenu)
theme.apply_global(ctk)

DB_PATH = db_path()
PHOTOS_DIR = photos_dir()
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

# ─── Штрихкод ────
BARCODE_PREFIX = "ARM"
DELETE_PASSWORD = "1234"  # смените на свой пароль

# ── модальные диалоги на Windows ─────────────────────────────
# Без parent=<окно приложения> messagebox/simpledialog создают диалог, не
# привязанный к активному окну, и на Windows наше окно при этом уходит на
# задний план (фокус возвращается не туда). Подменяем вызовы обёртками:
# всегда передаём владельца — активный Toplevel приложения — и после
# закрытия диалога возвращаем окно на передний план.
import tkinter.messagebox as _tkmb
import tkinter.simpledialog as _tksd


# Последнее окно, с которым работал пользователь (кликал/вводил данные).
# Фокус после модального диалога на Windows «уезжает», поэтому определять
# владельца по фокусу в момент вызова ненадёжно — запоминаем активное окно.
_LAST_ACTIVE_WINDOW = None
_ACTIVE_TRACKER_INSTALLED = False


def _install_active_tracker(root):
    """Привязывает к root обработчик: любое нажатие/фокус запоминает окно,
    в котором это произошло. Вызывается один раз при старте приложения."""
    global _ACTIVE_TRACKER_INSTALLED
    if _ACTIVE_TRACKER_INSTALLED:
        return
    _ACTIVE_TRACKER_INSTALLED = True
    try:
        def _on_focus(event=None):
            global _LAST_ACTIVE_WINDOW
            try:
                w = event.widget if event is not None else root.focus_get()
                if w is not None:
                    tl = w.winfo_toplevel()
                    if tl is not None:
                        _LAST_ACTIVE_WINDOW = tl
            except Exception:
                pass
        root.bind_all("<ButtonPress>", _on_focus, add="+")
        root.bind_all("<KeyPress>", _on_focus, add="+")
        root.bind_all("<FocusIn>", _on_focus, add="+")
    except Exception:
        pass


def _active_window():
    """Окно приложения, с которым пользователь работал последним (root или
    дочерний Toplevel).

    Ключевой момент: если открыто хотя бы одно дочернее окно (сетка и т.п.),
    никогда не возвращаем root — иначе после закрытия диалога поднимется
    главное окно, и рабочее (сетка) уйдёт в задний фон за ним.
    """
    try:
        root = ctk.CTk._default_root
        if root is None:
            root = tk._default_root
        if root is None:
            return None
        _install_active_tracker(root)
        global _LAST_ACTIVE_WINDOW
        # 1) Текущий фокус — самое точное.
        for w in (root.focus_get(), root.focus_displayof()):
            if w is not None:
                tl = w.winfo_toplevel()
                if tl is not None:
                    if tl is not root:
                        _LAST_ACTIVE_WINDOW = tl
                        return tl
        # 2) Последнее запомненное окно, если ещё живо и это не root.
        if _LAST_ACTIVE_WINDOW is not None:
            try:
                if _LAST_ACTIVE_WINDOW.winfo_exists() and _LAST_ACTIVE_WINDOW is not root:
                    return _LAST_ACTIVE_WINDOW
            except Exception:
                _LAST_ACTIVE_WINDOW = None
        # 3) Фокус не на дочернем окне (вызов из after/timer) — берём первое
        #    видимое дочернее окно, если оно есть; root — только в крайнем случае.
        for child in root.winfo_children():
            if isinstance(child, tk.Toplevel) and child.winfo_viewable():
                return child
        return root
    except Exception:
        return None


def _messagebox_owner():
    """Активное окно приложения (root или дочерний Toplevel) для привязки
    модального диалога — чтобы на Windows окно не уходило в задний план."""
    return _active_window()


# Окна приложения, которые делаем owned (transient) к главному окну.
# На Windows transient — это нативный owned-механизм: Windows сам держит
# owned-окно ПОВЕРХ родителя (не уходит в фон) и сам показывает его
# диалоги поверх окна. Это надёжнее topmost: topmost-окно прячет диалоги
# за собой, а owned-окно — нет.
_OWNED_WINDOWS = set()


def _keep_topmost(win):
    """Делает окно owned (transient) к главному окну приложения.

    Windows-механизм owned-окон:
      * owned-окно всегда поверх своего родителя — сетка не уходит в фон;
      * диалог с parent=owned-окно появляется ПОВЕРХ него;
      * после закрытия диалога Windows сам возвращает фокус owned-окну.
    """
    if win is None:
        return
    try:
        tl = win.winfo_toplevel()
        if tl in _OWNED_WINDOWS:
            return
        root = ctk.CTk._default_root
        if root is None:
            root = tk._default_root
        if root is None or tl is root:
            return
        tl.transient(root)
        _OWNED_WINDOWS.add(tl)

        def _cleanup(event=None):
            _OWNED_WINDOWS.discard(tl)
        try:
            tl.bind("<Destroy>", _cleanup, add="+")
        except Exception:
            pass
    except Exception:
        pass


def _force_foreground(win):
    """Гарантированно поднимает окно поверх других окон ПРИЛОЖЕНИЯ на Windows.
    SetForegroundWindow в этот момент разрешён — окно только что закрыло
    модальный диалог, и приложение активно (не перехват чужих окон)."""
    if win is None:
        return
    try:
        import ctypes
        tl = win.winfo_toplevel()
        hwnd = tl.winfo_id()
        user32 = ctypes.windll.user32
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        # SetWindowPos без флага HWND_TOPMOST: просто поднять в Z-порядке,
        # НЕ делая окно «всегда поверх» — иначе диалоги будут прятаться за ним.
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
    except Exception:
        pass


def _raise_all_windows():
    """Поднимает все окна приложения на передний план (в т.ч. Toplevel'ы)."""
    try:
        root = ctk.CTk._default_root
        if root is None:
            root = tk._default_root
        if root is None:
            return
        # root.lift() и root.focus_force() НЕ вызываем: главное окно не должно
        # перекрывать дочерние (сетка и т.п.) и забирать у них фокус.
        for child in root.winfo_children():
            if isinstance(child, tk.Toplevel) and child.winfo_viewable():
                child.lift()
                _force_foreground(child)
    except Exception:
        pass


def _with_owner(fn):
    def wrapped(*args, **kwargs):
        # Запоминаем активное окно ДО показа диалога: после закрытия модального
        # диалога фокус на Windows уходит, и без этого следующий диалог
        # привяжется не к тому окну.
        global _LAST_ACTIVE_WINDOW
        _LAST_ACTIVE_WINDOW = _active_window() or _LAST_ACTIVE_WINDOW
        parent = kwargs.get("parent")
        # Владелец: явно переданный parent (self) надёжнее, чем фокус —
        # после предыдущего модального диалога фокус может «уехать» на
        # главное окно, и тогда окно сетки после закрытия уйдёт в фон.
        owner = parent
        if owner is None:
            owner = _messagebox_owner()
        if owner is not None:
            kwargs["parent"] = owner
        # Рабочие окна (сетки и т.п.) делаем owned (transient) к главному окну:
        # Windows сам держит их поверх родителя и сам показывает их диалоги
        # поверх окна. Главное окно (root) не трогаем.
        owner_tl = None
        if owner is not None:
            try:
                owner_tl = owner.winfo_toplevel()
                _keep_topmost(owner_tl)
            except Exception:
                pass
        try:
            return fn(*args, **kwargs)
        finally:
            # Windows с transient-окном сам возвращает фокус владельцу после
            # закрытия модального диалога, но для надёжности дополнительно
            # поднимаем окно на передний план.
            _raise_all_windows()
            if owner is not None:
                try:
                    _force_foreground(owner)
                    owner.focus_force()
                except Exception:
                    pass
    return wrapped


for _name in ("askyesno", "askokcancel", "askquestion", "askretrycancel",
              "showinfo", "showwarning", "showerror"):
    setattr(_tkmb, _name, _with_owner(getattr(_tkmb, _name)))
for _name in ("askstring", "askinteger", "askfloat"):
    setattr(_tksd, _name, _with_owner(getattr(_tksd, _name)))


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
# Тренерское звание — не путать со спортивным разрядом (RANKS) выше.
# Синхронизирован с COACH_QUALIFICATIONS в backend/app/schemas/coaches.py
# и со списком в frontend/src/pages/admin/Coaches/CoachesAdmin.tsx.
COACH_QUALIFICATIONS = [
    "Без категории",
    "Тренер II категории",
    "Тренер I категории",
    "Тренер высшей категории",
    "Заслуженный тренер РК",
]
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


# ─── Папка в Cloudinary для фото участников турнира ──────────
# Cloudinary создаёт папки сам (параметр folder, вложенность через '/'),
# поэтому отдельного API для "создания папки" не нужно. Имя папки
# транслитерируем в латиницу, чтобы в Cloudinary Media Library не было
# кириллицы и проблем с URL-кодированием.
_TRANSLIT = {
    ord("а"): "a", ord("б"): "b", ord("в"): "v", ord("г"): "g",
    ord("д"): "d", ord("е"): "e", ord("ё"): "yo", ord("ж"): "zh",
    ord("з"): "z", ord("и"): "i", ord("й"): "y", ord("к"): "k",
    ord("л"): "l", ord("м"): "m", ord("н"): "n", ord("о"): "o",
    ord("п"): "p", ord("р"): "r", ord("с"): "s", ord("т"): "t",
    ord("у"): "u", ord("ф"): "f", ord("х"): "kh", ord("ц"): "ts",
    ord("ч"): "ch", ord("ш"): "sh", ord("щ"): "sch", ord("ъ"): "",
    ord("ы"): "y", ord("ь"): "", ord("э"): "e", ord("ю"): "yu",
    ord("я"): "ya",
}


def tournament_photo_folder(name):
    """'Чемпионат города-2026' -> 'competitions/chempionat-goroda-2026'.
    Возвращает None для пустого имени — тогда участники без фото."""
    if not name:
        return None
    s = name.strip().lower().translate(_TRANSLIT)
    s = "".join(ch if ch.isalnum() else "-" for ch in s)
    s = "-".join(part for part in s.split("-") if part)
    return f"competitions/{s}" if s else None



def extract_birth_year(birth_date_str):
    """Достаёт год рождения независимо от формата строки. Основной формат
    в десктопе — 'DD.MM.YYYY', но из-за старого бага в pull_sync (до
    конвертации ISO-дат с сервера через _to_desktop_date) в локальной БД
    могли остаться записи в формате 'YYYY-MM-DD' — падать на них не
    должны ни карточка спортсмена, ни расчёт возрастной категории."""
    if not birth_date_str:
        return datetime.now().year
    s = str(birth_date_str).strip()
    if "." in s:
        year_part = s.split(".")[-1]
    elif "-" in s:
        parts = s.split("-")
        # YYYY-MM-DD -> год первым; на всякий случай берём 4-значную часть
        year_part = parts[0] if len(parts[0]) == 4 else parts[-1]
    else:
        year_part = s
    try:
        return int(year_part)
    except ValueError:
        return datetime.now().year


def birth_age_label(birth_date_str):
    """'ДД.ММ.ГГГГ' -> 'ДД.ММ.ГГГГ (N лет)' с точным возрастом на сегодня.
    Понимает и ISO 'ГГГГ-ММ-ДД' (наследие старого pull_sync)."""
    if not birth_date_str:
        return ""
    s = str(birth_date_str).strip()
    try:
        bd = datetime.strptime(s, "%d.%m.%Y")
    except ValueError:
        try:
            bd = datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            return s
    today = datetime.now()
    age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
    return f"{bd.strftime('%d.%m.%Y')} ({age} лет)"


def load_photo_thumbnail(path, width, height):
    """Открывает фото и готовит качественный превью нужного размера:
    сначала центр-кроп под целевые пропорции (чтобы не растягивать лицо),
    затем масштабирование фильтром LANCZOS (значительно чётче, чем
    обычный .resize() по умолчанию — особенно при уменьшении с телефонных
    фото высокого разрешения)."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)  # уважаем поворот с камеры телефона
    src_w, src_h = img.size
    target_ratio = width / height
    src_ratio = src_w / src_h
    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        img = img.crop((left, 0, left + new_w, src_h))
    else:
        new_h = int(src_w / target_ratio)
        top = (src_h - new_h) // 2
        img = img.crop((0, top, src_w, top + new_h))
    img = img.resize((width, height), Image.LANCZOS)
    img = round_corners(img, max(6, min(width, height) // 8))
    return img


def round_corners(img, radius):
    """Скругляет углы изображения через альфа-маску — фото в карточках
    получает мягкие края вместо жёстких прямоугольных углов."""
    img = img.convert("RGBA")
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    img.putalpha(mask)
    return img


def center_toplevel(win, width, height):
    """Центрирует Toplevel-окно (width x height) относительно всего экрана.
    Окно должно быть ещё в withdraw()/не отрисовано — вызываем ДО deiconify(),
    иначе на некоторых WM виден скачок из угла в центр."""
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    x = max(0, (sw - width) // 2)
    y = max(0, (sh - height) // 2)
    win.geometry(f"{width}x{height}+{x}+{y}")


AGE_LEVEL_LABELS = OrderedDict([
    (0, "До 15 лет (Sub-Junior)"),
    (1, "16-18 лет (Junior)"),
    (2, "19-23 лет (Youth)"),
    (3, "24+ лет (Senior)"),
])


def get_age_level(birth_date_str, tournament_year=None):
    """Возрастной уровень (0..3) по году рождения — общий для
    compute_age_category и фильтра в окне 'Спортсмены'."""
    if tournament_year is None:
        tournament_year = datetime.now().year
    birth_year = extract_birth_year(birth_date_str)
    turning_age = tournament_year - birth_year
    if turning_age <= 15:
        return 0
    elif turning_age <= 18:
        return 1
    elif turning_age <= 23:
        return 2
    return 3


def compute_age_category(birth_date_str, gender, tournament_year=None):
    """Считает возраст по календарному году (turning age), не по точной дате."""
    level = get_age_level(birth_date_str, tournament_year)

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
        # Встроенный SQL lower() у SQLite понимает только ASCII и не трогает
        # кириллицу («Иванов» → «Иванов», а не «иванов») — из-за этого поиск
        # по ФИО (тренеры, спортсмены) не находил вообще ничего при вводе на
        # русском. Подменяем на Python-реализацию str.lower(), которая
        # корректно работает с юникодом — чинит все места, использующие
        # lower(...) LIKE ? одним махом.
        self.conn.create_function("lower", 1, lambda s: s.lower() if s is not None else None)
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
        CREATE INDEX IF NOT EXISTS idx_matches_category_hand ON matches(category_id, hand);
        CREATE INDEX IF NOT EXISTS idx_matches_category_hand_status ON matches(category_id, hand, status);
        CREATE TABLE IF NOT EXISTS athletes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            birth_date TEXT NOT NULL,        -- 'YYYY-MM-DD'
            gender TEXT NOT NULL CHECK (gender IN ('M','F')),
            club TEXT,
            club_id INTEGER,                 -- ссылка на клуб (реестр «Клубы»)
            rank TEXT,                       -- звание
            photo_path TEXT,
            is_hidden INTEGER DEFAULT 0,     -- скрыт через админку сайта
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS coaches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            first_name TEXT,
            last_name TEXT,
            birth_date TEXT,                 -- 'YYYY-MM-DD' (для расчёта возраста)
iin TEXT,                        -- ИИН, 12 цифр
            phone TEXT,                     -- телефон 8(XXX)XXX-XX-XX
            qualification TEXT,              -- тренерское звание
            city TEXT,                       -- Город/Район
            club TEXT,
            club_id INTEGER,                 -- ссылка на клуб (реестр «Клубы»)
            photo_path TEXT,
            bio TEXT,
            is_hidden INTEGER DEFAULT 0,     -- скрыт через админку сайта
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS clubs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            city TEXT,                       -- Город/Область
            address TEXT,                    -- Адрес зала
            phone TEXT,                      -- телефон 8(XXX)XXX-XX-XX
            founded_year INTEGER,
            logo_path TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
                          
        CREATE TABLE IF NOT EXISTS dvoeborie_overrides (
            tournament_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            pid INTEGER NOT NULL,
            manual_rank INTEGER NOT NULL,
            PRIMARY KEY (tournament_id, category_id, pid)
        );
        CREATE TABLE IF NOT EXISTS bracket_generations (
            category_id INTEGER NOT NULL,
            hand TEXT NOT NULL,
            generation INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (category_id, hand)
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
        if "photo_folder" not in t_cols:
            self.conn.execute("ALTER TABLE tournaments ADD COLUMN photo_folder TEXT")
        # Бэкфилл: турниры, созданные до появления папок в Cloudinary (или в
        # старой версии приложения), получают папку по названию — иначе их
        # участники продолжали бы падать в общую папку "athletes".
        for row in self.conn.execute(
                "SELECT id, name FROM tournaments WHERE photo_folder IS NULL").fetchall():
            folder = tournament_photo_folder(row["name"])
            if folder:
                self.conn.execute(
                    "UPDATE tournaments SET photo_folder=? WHERE id=?",
                    (folder, row["id"]))

        # Сессия соревнования для переноса между компьютерами
        # (экспорт/импорт .armwrestling): uuid сессии, созданный при
        # экспорте; при импорте на другом устройстве выдаётся новая сессия.
        if "session_id" not in t_cols:
            self.conn.execute("ALTER TABLE tournaments ADD COLUMN session_id TEXT")

        self.conn.commit()
        # Журнал переносов: что и откуда импортировалось (для предупреждения
        # «соревнование уже восстановлено на другом устройстве»).
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS transfer_marks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
            previous_session_id TEXT,
            imported_from TEXT,
            imported_at TEXT DEFAULT (datetime('now'))
        )
        """)
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

        a_cols = [r[1] for r in self.conn.execute("PRAGMA table_info(athletes)").fetchall()]
        if "coach_id" not in a_cols:
            self.conn.execute("ALTER TABLE athletes ADD COLUMN coach_id INTEGER REFERENCES coaches(id)")
        for table in ("athletes", "coaches"):
            cols = [r[1] for r in self.conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if "club_id" not in cols:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN club_id INTEGER")

        cl_cols = [r[1] for r in self.conn.execute("PRAGMA table_info(clubs)").fetchall()]
        if "address" not in cl_cols:
            self.conn.execute("ALTER TABLE clubs ADD COLUMN address TEXT")
        if "phone" not in cl_cols:
            self.conn.execute("ALTER TABLE clubs ADD COLUMN phone TEXT")
            # Бэкфилл случайным казахстанским номером (как на сервере), чтобы
            # у существующих клубов был контакт для «Связаться».
            import random as _random
            for row in self.conn.execute("SELECT id FROM clubs").fetchall():
                code = _random.choice(["700", "701", "702", "705", "708", "747", "775", "776", "777", "778"])
                rest = f"{_random.randint(0, 9999999):07d}"
                self.conn.execute(
                    "UPDATE clubs SET phone=? WHERE id=?",
                    (f"8({code}){rest[0:3]}-{rest[3:5]}-{rest[5:]}", row[0]),
                )
        self.conn.commit()

        # ─── Карточка тренера: Имя/Фамилия/возраст/ИИН/звание/город ───
        c_cols = [r[1] for r in self.conn.execute("PRAGMA table_info(coaches)").fetchall()]
        for col in ("first_name", "last_name", "birth_date", "iin", "qualification", "city", "phone"):
            if col not in c_cols:
                self.conn.execute(f"ALTER TABLE coaches ADD COLUMN {col} TEXT")
        if "is_hidden" not in c_cols:
            self.conn.execute("ALTER TABLE coaches ADD COLUMN is_hidden INTEGER DEFAULT 0")
        if "phone" in c_cols:
            self.conn.execute(
                "UPDATE coaches SET phone = '8(702)313-53-83' WHERE phone IS NULL OR phone = ''"
            )
        self.conn.commit()

        a_cols = [r[1] for r in self.conn.execute("PRAGMA table_info(athletes)").fetchall()]
        if "iin" not in a_cols:
            self.conn.execute("ALTER TABLE athletes ADD COLUMN iin TEXT")
        if "phone" not in a_cols:
            self.conn.execute("ALTER TABLE athletes ADD COLUMN phone TEXT")
        for col in ("join_club_date", "last_competition_date", "next_inactive_date"):
            if col not in a_cols:
                self.conn.execute(f"ALTER TABLE athletes ADD COLUMN {col} TEXT")
        if "is_hidden" not in a_cols:
            self.conn.execute("ALTER TABLE athletes ADD COLUMN is_hidden INTEGER DEFAULT 0")
        if "club_active" not in a_cols:
            self.conn.execute("ALTER TABLE athletes ADD COLUMN club_active INTEGER DEFAULT 0")
        self.conn.commit()

        # ─── Система рейтинга клубов: таблица баллов и журнал изменений ───
        cur.execute("""
        CREATE TABLE IF NOT EXISTS club_rating (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            club_id INTEGER NOT NULL UNIQUE REFERENCES clubs(id) ON DELETE CASCADE,
            rating INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS club_rating_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            club_id INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
            athlete_id INTEGER REFERENCES athletes(id) ON DELETE SET NULL,
            tournament_id INTEGER REFERENCES tournaments(id) ON DELETE CASCADE,
            points INTEGER NOT NULL,
            reason TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)
        crh_cols = [r[1] for r in self.conn.execute("PRAGMA table_info(club_rating_history)").fetchall()]
        if "reason" not in crh_cols:
            self.conn.execute("ALTER TABLE club_rating_history ADD COLUMN description TEXT DEFAULT ''")
        self.conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_club_rating_history
            ON club_rating_history (club_id, athlete_id, tournament_id, reason, description)
        """)
        self.conn.execute("""
        CREATE INDEX IF NOT EXISTS ix_club_rating_history_club
            ON club_rating_history (club_id, created_at)
        """)
        self.conn.commit()

        rows = self.conn.execute("SELECT id, birth_date FROM athletes WHERE iin IS NULL OR iin=''").fetchall()
        for r in rows:
            if r["birth_date"]:
                try:
                    bd = datetime.strptime(r["birth_date"], "%d.%m.%Y")
                    prefix = bd.strftime("%y%m%d")
                except:
                    prefix = datetime.now().strftime("%y%m%d")
            else:
                prefix = datetime.now().strftime("%y%m%d")
            suffix = f"{random.randint(0, 999999):06d}"
            iin = prefix + suffix
            self.conn.execute("UPDATE athletes SET iin=? WHERE id=?", (iin, r["id"]))
        self.conn.commit()

    def create_tournament(self, name, date, location="", weight_tolerance=0,
                          bracket_system="double", format_type="separate"):
        cur = self.conn.execute(
            "INSERT INTO tournaments (name, date, location, weight_tolerance, "
            "bracket_system, format_type, photo_folder, status) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (name, date, location, weight_tolerance, bracket_system,
             format_type, tournament_photo_folder(name), "upcoming"))
        self.conn.commit()
        return cur.lastrowid

    def start_tournament(self, tid):
        """Переводит турнир из «скоро начнётся» в активное состояние (идёт)."""
        self.conn.execute(
            "UPDATE tournaments SET status='active' WHERE id=?", (tid,))
        self.conn.commit()

    def get_tournaments(self):
        return self.conn.execute("SELECT * FROM tournaments ORDER BY date DESC").fetchall()

    def get_tournament(self, tid):
        return self.conn.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()

    def delete_tournament(self, tid):
        # PRAGMA foreign_keys=ON не включён (SQLite выключен по умолчанию),
        # поэтому ON DELETE CASCADE из схемы НЕ срабатывает автоматически.
        # Удаляем связанные записи вручную (как в delete_athlete), чтобы не
        # оставлять orphan-записи (участники/матчи/категории удалённого турнира).
        cats = [r["id"] for r in self.conn.execute(
            "SELECT id FROM weight_categories WHERE tournament_id=?", (tid,))]
        if cats:
            marks = ",".join("?" * len(cats))
            self.conn.execute(
                f"DELETE FROM bracket_generations WHERE category_id IN ({marks})", tuple(cats))
        self.conn.execute("DELETE FROM matches WHERE tournament_id=?", (tid,))
        self.conn.execute("DELETE FROM participants WHERE tournament_id=?", (tid,))
        self.conn.execute("DELETE FROM dvoeborie_overrides WHERE tournament_id=?", (tid,))
        self.conn.execute("DELETE FROM club_rating_history WHERE tournament_id=?", (tid,))
        self.conn.execute("DELETE FROM transfer_marks WHERE tournament_id=?", (tid,))
        self.conn.execute("DELETE FROM weight_categories WHERE tournament_id=?", (tid,))
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
        # FK-каскад не срабатывает (PRAGMA foreign_keys=ON не включён) —
        # удаляем зависимые матчи/участников/переопределения вручную.
        self.conn.execute("DELETE FROM matches WHERE category_id=?", (cid,))
        self.conn.execute("DELETE FROM participants WHERE category_id=?", (cid,))
        self.conn.execute("DELETE FROM dvoeborie_overrides WHERE category_id=?", (cid,))
        self.conn.execute("DELETE FROM bracket_generations WHERE category_id=?", (cid,))
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

    def add_athlete(self, first_name, last_name, birth_date, gender, club="", rank="",
                     photo_path="", coach_id=None, iin="", phone="", club_id=None):
        cur = self.conn.execute(
            "INSERT INTO athletes (first_name,last_name,birth_date,gender,club,rank,photo_path,coach_id,iin,phone,club_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (first_name, last_name, birth_date, gender, club, rank, photo_path, coach_id, iin, phone, club_id))
        self.conn.commit()
        return cur.lastrowid

    def update_athlete(self, aid, first_name, last_name, birth_date, gender, club, rank,
                        photo_path, coach_id=None, iin=None, phone=None, club_id=None):
        self.conn.execute(
            "UPDATE athletes SET first_name=?,last_name=?,birth_date=?,gender=?,club=?,rank=?,"
            "photo_path=?,coach_id=?,iin=?,phone=?,club_id=? WHERE id=?",
            (first_name, last_name, birth_date, gender, club, rank, photo_path, coach_id, iin, phone, club_id, aid))
        self.conn.commit()

    # ── тренеры ──────────────────────────────────────────────────
    def add_coach(self, full_name, club="", photo_path="", bio="",
                  first_name="", last_name="", birth_date="", iin="",
                  qualification="", city="", phone="", club_id=None):
        cur = self.conn.execute(
            "INSERT INTO coaches (full_name, club, photo_path, bio, first_name, "
            "last_name, birth_date, iin, qualification, city, phone, club_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (full_name, club, photo_path, bio, first_name, last_name,
             birth_date, iin, qualification, city, phone, club_id))
        self.conn.commit()
        return cur.lastrowid

    def update_coach(self, cid, full_name, club="", photo_path="", bio="",
                      first_name="", last_name="", birth_date="", iin="",
                      qualification="", city="", phone="", club_id=None):
        self.conn.execute(
            "UPDATE coaches SET full_name=?, club=?, photo_path=?, bio=?, first_name=?, "
            "last_name=?, birth_date=?, iin=?, qualification=?, city=?, phone=?, club_id=? WHERE id=?",
            (full_name, club, photo_path, bio, first_name, last_name,
             birth_date, iin, qualification, city, phone, club_id, cid))
        self.conn.commit()

    def delete_coach(self, cid):
        # Отвязываем учеников ДО удаления самого тренера — coach_id не
        # объявлен с ON DELETE в схеме, битые ссылки после DELETE иначе
        # останутся (та же логика, что и в delete_athlete для athlete_id
        # участников).
        self.conn.execute("UPDATE athletes SET coach_id=NULL WHERE coach_id=?", (cid,))
        self.conn.execute("DELETE FROM coaches WHERE id=?", (cid,))
        self.conn.commit()

    def get_coaches(self, query=""):
        # Скрытые через админку сайта карточки (is_hidden=1) не показываем
        # среди обычных — они живут в отдельной секции «Скрытые».
        base = "SELECT * FROM coaches WHERE COALESCE(is_hidden,0)=0"
        if query:
            like = f"%{query.lower()}%"
            return self.conn.execute(
                base + " AND lower(full_name) LIKE ? ORDER BY full_name",
                (like,)).fetchall()
        return self.conn.execute(base + " ORDER BY full_name").fetchall()

    def search_hidden_coaches(self, query=""):
        base = "SELECT * FROM coaches WHERE COALESCE(is_hidden,0)=1"
        if query:
            like = f"%{query.lower()}%"
            return self.conn.execute(
                base + " AND lower(full_name) LIKE ? ORDER BY full_name",
                (like,)).fetchall()
        return self.conn.execute(base + " ORDER BY full_name").fetchall()

    def count_hidden_coaches(self):
        return self.conn.execute(
            "SELECT COUNT(*) FROM coaches WHERE COALESCE(is_hidden,0)=1"
        ).fetchone()[0]

    def set_coach_hidden(self, cid, hidden):
        if hidden:
            # Скрытие = удаление: тренер выходит из клуба и отпускает всех
            # учеников (зеркально серверу — admin/coaches.py update_coach).
            # «Показать» ничего не восстанавливает.
            self.conn.execute(
                "UPDATE athletes SET coach_id=NULL WHERE coach_id=?", (cid,))
            self.conn.execute(
                "UPDATE coaches SET is_hidden=1, club_id=NULL, club='' WHERE id=?",
                (cid,))
        else:
            self.conn.execute("UPDATE coaches SET is_hidden=0 WHERE id=?", (cid,))
        self.conn.commit()

    def get_coach(self, cid):
        return self.conn.execute("SELECT * FROM coaches WHERE id=?", (cid,)).fetchone()

    def get_athletes_by_coach(self, coach_id):
        return self.conn.execute(
            "SELECT * FROM athletes WHERE coach_id=? AND COALESCE(is_hidden,0)=0 "
            "ORDER BY last_name", (coach_id,)
        ).fetchall()

    def delete_athlete(self, aid):
        # Удаление спортсмена из клуба: штраф -10 рейтингу клуба (зеркально
        # серверу — admin/athletes.py delete_athlete). Делаем ДО удаления
        # карточки, чтобы history.athlete_id ещё указывал на спортсмена.
        row = self.conn.execute(
            "SELECT club_id FROM athletes WHERE id=?", (aid,)).fetchone()
        if row and row["club_id"]:
            from club_rating import apply_athlete_removed
            apply_athlete_removed(self.conn, aid, row["club_id"])

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
        # Скрытые через админку сайта карточки (is_hidden=1) не показываем
        # среди обычных — они живут в отдельной секции «Скрытые».
        base = ("SELECT athletes.*, coaches.full_name AS coach_name FROM athletes "
                "LEFT JOIN coaches ON coaches.id = athletes.coach_id "
                "WHERE COALESCE(athletes.is_hidden,0)=0")
        if query:
            like = f"%{query.lower()}%"
            return self.conn.execute(
                base + " AND lower(athletes.first_name || ' ' || athletes.last_name) LIKE ? "
                       "ORDER BY athletes.last_name",
                (like,)).fetchall()
        return self.conn.execute(base + " ORDER BY athletes.last_name").fetchall()

    def search_hidden_athletes(self, query=""):
        base = ("SELECT athletes.*, coaches.full_name AS coach_name FROM athletes "
                "LEFT JOIN coaches ON coaches.id = athletes.coach_id "
                "WHERE COALESCE(athletes.is_hidden,0)=1")
        if query:
            like = f"%{query.lower()}%"
            return self.conn.execute(
                base + " AND lower(athletes.first_name || ' ' || athletes.last_name) LIKE ? "
                       "ORDER BY athletes.last_name",
                (like,)).fetchall()
        return self.conn.execute(base + " ORDER BY athletes.last_name").fetchall()

    def count_athletes(self):
        return self.conn.execute(
            "SELECT COUNT(*) FROM athletes WHERE COALESCE(is_hidden,0)=0"
        ).fetchone()[0]

    def count_hidden_athletes(self):
        return self.conn.execute(
            "SELECT COUNT(*) FROM athletes WHERE COALESCE(is_hidden,0)=1"
        ).fetchone()[0]

    def set_athlete_hidden(self, aid, hidden):
        if hidden:
            # Скрытие = удаление: спортсмен выходит из клуба (штраф -10,
            # зеркально серверу) и от тренера. «Показать» ничего не
            # восстанавливает — привязки придётся делать заново.
            row = self.conn.execute(
                "SELECT club_id, coach_id FROM athletes WHERE id=?", (aid,)).fetchone()
            if row and row["club_id"]:
                from club_rating import apply_athlete_removed
                apply_athlete_removed(self.conn, aid, row["club_id"])
            self.conn.execute(
                "UPDATE athletes SET is_hidden=1, club_id=NULL, coach_id=NULL, "
                "club='', join_club_date=NULL, last_competition_date=NULL, "
                "next_inactive_date=NULL, club_active=0 WHERE id=?", (aid,))
        else:
            self.conn.execute("UPDATE athletes SET is_hidden=0 WHERE id=?", (aid,))
        self.conn.commit()

    def get_athlete(self, aid):
        return self.conn.execute("SELECT * FROM athletes WHERE id=?", (aid,)).fetchone()

    # ── поиск по ИИН (уникальность: один спортсмен = один ИИН) ─────
    def find_athlete_by_iin(self, iin, exclude_id=None):
        if exclude_id:
            return self.conn.execute(
                "SELECT id, first_name, last_name FROM athletes WHERE iin=? AND id!=?",
                (iin, exclude_id)).fetchone()
        return self.conn.execute(
            "SELECT id, first_name, last_name FROM athletes WHERE iin=?", (iin,)).fetchone()

    def find_coach_by_iin(self, iin, exclude_id=None):
        if exclude_id:
            return self.conn.execute(
                "SELECT id, full_name FROM coaches WHERE iin=? AND id!=?",
                (iin, exclude_id)).fetchone()
        return self.conn.execute(
            "SELECT id, full_name FROM coaches WHERE iin=?", (iin,)).fetchone()

    # ── возможные дубли по ФИО + дате рождения (только предупреждение) ──
    def _norm_date(self, s):
        # в локальной БД дата в ДД.ММ.ГГГГ, с сервера может прийти ГГГГ-ММ-ДД —
        # приводим к одному виду перед сравнением
        s = (s or "").strip()
        if not s:
            return None
        for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(s[:10], fmt).strftime("%d.%m.%Y")
            except ValueError:
                continue
        return s

    def find_duplicate_athlete(self, first_name, last_name, birth_date, exclude_id=None):
        """Ищет спортсмена с такими же ФИО (без учёта регистра) и датой
        рождения. Нужно только для предупреждения — сохранение не блокирует."""
        fn = first_name.strip().lower()
        ln = last_name.strip().lower()
        if not fn or not ln or not birth_date:
            return None
        bd = self._norm_date(birth_date)
        if bd is None:
            return None
        rows = self.conn.execute(
            "SELECT id, first_name, last_name, birth_date FROM athletes "
            "WHERE COALESCE(is_hidden,0)=0 AND lower(first_name)=? AND lower(last_name)=?",
            (fn, ln)).fetchall()
        for r in rows:
            if exclude_id is not None and r["id"] == exclude_id:
                continue
            if self._norm_date(r["birth_date"]) == bd:
                return r
        return None

    def find_duplicate_coach(self, full_name, birth_date, exclude_id=None):
        fn = full_name.strip().lower()
        if not fn or not birth_date:
            return None
        bd = self._norm_date(birth_date)
        if bd is None:
            return None
        rows = self.conn.execute(
            "SELECT id, full_name, birth_date FROM coaches "
            "WHERE COALESCE(is_hidden,0)=0 AND lower(full_name)=?",
            (fn,)).fetchall()
        for r in rows:
            if exclude_id is not None and r["id"] == exclude_id:
                continue
            if self._norm_date(r["birth_date"]) == bd:
                return r
        return None

    # ── клубы ──────────────────────────────────────────────────
    def get_clubs(self, query=""):
        if query:
            like = f"%{query.lower()}%"
            return self.conn.execute(
                "SELECT * FROM clubs WHERE lower(name) LIKE ? ORDER BY name",
                (like,)).fetchall()
        return self.conn.execute("SELECT * FROM clubs ORDER BY name").fetchall()

    def get_club(self, cid):
        return self.conn.execute("SELECT * FROM clubs WHERE id=?", (cid,)).fetchone()

    def add_club(self, name, city="", address="", founded_year=None, logo_path="", phone=""):
        cur = self.conn.execute(
            "INSERT INTO clubs (name, city, address, founded_year, logo_path, phone) VALUES (?,?,?,?,?,?)",
            (name, city, address, founded_year, logo_path, phone))
        self.conn.commit()
        return cur.lastrowid

    def update_club(self, cid, name, city="", address="", founded_year=None, logo_path="", phone=""):
        self.conn.execute(
            "UPDATE clubs SET name=?, city=?, address=?, founded_year=?, logo_path=?, phone=? WHERE id=?",
            (name, city, address, founded_year, logo_path, phone, cid))
        # Переименование клуба должно обновить и карточки спортсменов/тренеров,
        # которые на него ссылаются (club_id), — иначе в реестре останется
        # старое название.
        self.conn.execute("UPDATE athletes SET club=? WHERE club_id=?", (name, cid))
        self.conn.execute("UPDATE coaches SET club=? WHERE club_id=?", (name, cid))
        self.conn.commit()

    def delete_club(self, cid):
        # Отвязываем спортсменов и тренеров ДО удаления клуба — иначе
        # битые club_id останутся в карточках.
        self.conn.execute("UPDATE athletes SET club_id=NULL, club=NULL WHERE club_id=?", (cid,))
        self.conn.execute("UPDATE coaches SET club_id=NULL, club=NULL WHERE club_id=?", (cid,))
        self.conn.execute("DELETE FROM clubs WHERE id=?", (cid,))
        self.conn.commit()

    def get_athletes_by_club(self, club_id):
        return self.conn.execute(
            "SELECT * FROM athletes WHERE club_id=? ORDER BY last_name", (club_id,)
        ).fetchall()

    def get_coaches_by_club(self, club_id):
        return self.conn.execute(
            "SELECT * FROM coaches WHERE club_id=? ORDER BY full_name", (club_id,)
        ).fetchall()

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

    def get_dvoeborie_overrides(self, tournament_id, category_id):
        """Ручные места жюри в двоеборье: {pid: manual_rank}."""
        rows = self.conn.execute(
            "SELECT pid, manual_rank FROM dvoeborie_overrides "
            "WHERE tournament_id=? AND category_id=?",
            (tournament_id, category_id)).fetchall()
        return {r["pid"]: r["manual_rank"] for r in rows}

    def set_dvoeborie_override(self, tournament_id, category_id, pid, manual_rank):
        self.conn.execute(
            "INSERT INTO dvoeborie_overrides (tournament_id, category_id, pid, manual_rank) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(tournament_id, category_id, pid) "
            "DO UPDATE SET manual_rank=excluded.manual_rank",
            (tournament_id, category_id, pid, manual_rank))
        self.conn.commit()

    def clear_dvoeborie_overrides(self, tournament_id, category_id, pids=None):
        if pids:
            qmarks = ",".join("?" * len(pids))
            self.conn.execute(
                "DELETE FROM dvoeborie_overrides "
                "WHERE tournament_id=? AND category_id=? AND pid IN (" + qmarks + ")",
                (tournament_id, category_id, *pids))
        else:
            self.conn.execute(
                "DELETE FROM dvoeborie_overrides WHERE tournament_id=? AND category_id=?",
                (tournament_id, category_id))
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

    def get_bracket_generation(self, category_id, hand):
        """Номер поколения сетки (0 — первая). Растёт при сбросе сетки,
        поэтому «Сбросить сетку» + «Создать сетку» дают НОВУЮ случайную
        сетку, а простое повторное «Создать» — ту же самую."""
        row = self.conn.execute(
            "SELECT generation FROM bracket_generations WHERE category_id=? AND hand=?",
            (category_id, hand)).fetchone()
        return row["generation"] if row else 0

    def bump_bracket_generation(self, category_id, hand):
        """Увеличивает поколение сетки (вызывается при сбросе сетки)."""
        self.conn.execute(
            "INSERT INTO bracket_generations (category_id, hand, generation) VALUES (?, ?, 1) "
            "ON CONFLICT(category_id, hand) DO UPDATE SET generation = generation + 1",
            (category_id, hand))
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

    def get_broadcast_table_numbers(self, tournament_id, category_id, hand):
        """Множество номеров столов, занятых ДРУГИМИ сетками этого же
        турнира (категория+рука). Трансляция переживает закрытие окна
        (table_number живёт в БД), поэтому при проверке «свободных столов»
        мало смотреть на открытые окна — занятыми считаются и сохранённые
        номера. Столы других турниров не учитываются: они транслируются
        в другое время и на тех же номерах."""
        rows = self.conn.execute(
            "SELECT DISTINCT table_number FROM matches "
            "WHERE tournament_id=? AND table_number IS NOT NULL "
            "AND NOT (category_id=? AND hand=?)",
            (tournament_id, category_id, hand)).fetchall()
        return {r["table_number"] for r in rows}

    def get_participant(self, pid):
        if not pid:
            return None
        return self.conn.execute("SELECT * FROM participants WHERE id=?", (pid,)).fetchone()

    def get_participants_by_category(self, category_id):
        cur = self.conn.execute(
            "SELECT * FROM participants WHERE category_id=?", (category_id,))
        return [dict(row) for row in cur.fetchall()]

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
from sync.cloudinary_client import upload_photo, CloudinaryUploadError, is_configured  # noqa: E402
from sync.photo_cache import precache_photos, resolve_local_photo_path  # noqa: E402

# ─── Экспорт/импорт соревнования (.armwrestling), авто-бэкапы ──────
from transfer.backup_manager import BackupManager  # noqa: E402
from transfer.exporter import export_competition, ExportError, \
    validate_competition_integrity  # noqa: E402
from transfer.importer import import_competition, preview_archive, \
    CompetitionExistsError, IdCollisionError, ImportValidationError  # noqa: E402
from transfer.pack import BackupFormatError  # noqa: E402

backup_manager = BackupManager()
BACKUP_DIR = backups_dir()
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

_original_create_tournament = Database.create_tournament
_original_add_category = Database.add_category
_original_add_participant = Database.add_participant
_original_update_participant = Database.update_participant
_original_save_match = Database.save_match
_original_add_athlete = Database.add_athlete
_original_update_athlete = Database.update_athlete
_original_add_coach = Database.add_coach
_original_update_coach = Database.update_coach
_original_delete_coach = Database.delete_coach
_original_delete_tournament = Database.delete_tournament
_original_delete_category = Database.delete_category
_original_delete_participant = Database.delete_participant
_original_delete_athlete = Database.delete_athlete
_original_set_athlete_hidden = Database.set_athlete_hidden
_original_set_coach_hidden = Database.set_coach_hidden
_original_add_club = Database.add_club
_original_update_club = Database.update_club
_original_delete_club = Database.delete_club



def _synced_create_tournament(self, name, date, location="", weight_tolerance=0,
                              bracket_system="double", format_type="separate"):
    tid = _original_create_tournament(self, name, date, location, weight_tolerance,
                                      bracket_system, format_type)
    try:
        # Сетевой вызов (HTTP с таймаутом до 10с на попытку) уходит в фоновый
        # FIFO-воркер — создание турнира не замораживает диалог на офлайне.
        sync_manager.dispatch_async(lambda: sync_manager.on_tournament_created(
            tid, name, date, location, weight_tolerance, bracket_system, format_type))
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
        sync_manager.dispatch_async(lambda: sync_manager.on_category_created(
            tid, cid, name, sync_max_weight, hand, age_category))
    except Exception as e:
        print(f"[sync] add_category: {e}")
    return cid


def _synced_add_participant(self, tid, name, weight, club, category_id, hand="Обе",
                             photo_path="", age_category="Senior", athlete_id=None):
    pid = _original_add_participant(self, tid, name, weight, club, category_id,
                                     hand, photo_path, age_category, athlete_id)
    try:
        sync_manager.dispatch_async(lambda: sync_manager.on_participant_added(
            tid, pid, name, weight, club, category_id, hand, age_category,
            athlete_id=athlete_id))
    except Exception as e:
        print(f"[sync] add_participant: {e}")
    return pid


def _synced_update_participant(self, pid, name, weight, club, category_id, hand,
                                photo_path, age_category="Senior", athlete_id=None):
    _original_update_participant(self, pid, name, weight, club, category_id,
                                  hand, photo_path, age_category, athlete_id)
    tid = None
    try:
        row = self.conn.execute(
            "SELECT tournament_id FROM participants WHERE id=?", (pid,)).fetchone()
        tid = row["tournament_id"] if row else None
    except Exception:
        tid = None
    try:
        sync_manager.dispatch_async(lambda: sync_manager.on_participant_updated(
            tid, pid, name, weight, club, category_id, hand, age_category))
    except Exception as e:
        print(f"[sync] update_participant: {e}")


def _synced_save_match(self, match: dict):
    is_update = bool(match.get("id"))
    snapshot = dict(match)
    mid = _original_save_match(self, match)
    try:
        if is_update:
            # Неблокирующая отправка — ручное редактирование матча (счёт,
            # стол и т.п.) не должно подвешивать диалог на HTTP-запрос.
            sync_manager.dispatch_match_update_async(mid, snapshot)
        else:
            # Создание матча остаётся синхронным: оно обязано пройти ДО
            # следующих матчей (id_map и офлайн-очередь строятся по порядку),
            # на это завязаны тесты реальной синхронизации
            # (tests/stress/test_change_winner_real_sync.py). Асинхронная
            # отправка сюда ломала порядок и оставляла create_match в очереди.
            sync_manager.on_match_created(mid, match)
    except Exception as e:
        print(f"[sync] save_match: {e}")
    try:
        # Авто-бэкап после критической операции (завершение матча).
        if snapshot.get("status") == "done":
            backup_manager.request_backup()
    except Exception as e:
        print(f"[backup] hook: {e}")
    return mid

def _synced_add_athlete(self, first_name, last_name, birth_date, gender,
                         club="", rank="", photo_path="", coach_id=None,
                         iin="", phone="", club_id=None):
    aid = _original_add_athlete(self, first_name, last_name, birth_date,
                                 gender, club, rank, photo_path, coach_id,
                                 iin=iin, phone=phone, club_id=club_id)
    try:
        # Локальные данные (имя тренера) читаем здесь, на UI-потоке, а сам
        # сетевой вызов уходим в фоновый FIFO-воркер — добавление спортсмена
        # не должно замораживать интерфейс на HTTP-таймауты (как для матчей).
        coach = self.get_coach(coach_id) if coach_id else None
        coach_name = coach["full_name"] if coach else None
        sync_manager.dispatch_async(lambda: sync_manager.on_athlete_created(
            aid, first_name, last_name, birth_date, gender, club, rank,
            photo_path, coach_name=coach_name, iin=iin, phone=phone))
    except Exception as e:
        print(f"[sync] add_athlete: {e}")
    return aid


def _synced_update_athlete(self, aid, first_name, last_name, birth_date,
                            gender, club, rank, photo_path, coach_id=None,
                            iin=None, phone=None, club_id=None):
    _original_update_athlete(self, aid, first_name, last_name, birth_date,
                              gender, club, rank, photo_path, coach_id,
                              iin=iin, phone=phone, club_id=club_id)
    try:
        # coach_name всегда передаём явно ("" если тренер снят) — точно
        # так же, как first_name/birth_date/club выше передаются целиком,
        # а не как diff. Это даёт update_athlete на сервере однозначный
        # сигнал "тренер именно такой" вместо "не трогай поле".
        coach = self.get_coach(coach_id) if coach_id else None
        card = self.get_athlete(aid)
        is_hidden = card["is_hidden"] if card is not None and "is_hidden" in card.keys() else None
        coach_name = coach["full_name"] if coach else ""
        sync_manager.dispatch_async(lambda: sync_manager.on_athlete_updated(
            aid, first_name, last_name, birth_date, gender, club, rank,
            photo_path, coach_name=coach_name, iin=iin, phone=phone,
            is_hidden=is_hidden))
    except Exception as e:
        print(f"[sync] update_athlete: {e}")


def _synced_set_athlete_hidden(self, aid, hidden):
    _original_set_athlete_hidden(self, aid, hidden)
    try:
        card = self.get_athlete(aid)
        if card is None:
            return
        coach = self.get_coach(card["coach_id"]) if card["coach_id"] else None
        coach_name = coach["full_name"] if coach else ""
        sync_manager.dispatch_async(lambda: sync_manager.on_athlete_updated(
            aid, card["first_name"], card["last_name"], card["birth_date"],
            card["gender"], card["club"], card["rank"], card["photo_path"],
            coach_name=coach_name,
            iin=card["iin"], phone=card["phone"], is_hidden=bool(hidden)))
    except Exception as e:
        print(f"[sync] set_athlete_hidden: {e}")

def _synced_add_coach(self, full_name, club="", photo_path="", bio="",
                       first_name="", last_name="", birth_date="", iin="",
                       qualification="", city="", phone="", club_id=None):
    cid = _original_add_coach(self, full_name, club, photo_path, bio,
                               first_name, last_name, birth_date, iin,
                               qualification, city, phone, club_id)
    try:
        sync_manager.dispatch_async(lambda: sync_manager.on_coach_created(
            cid, full_name, club, photo_path, bio,
            first_name=first_name, last_name=last_name, birth_date=birth_date,
            iin=iin, qualification=qualification, city=city, phone=phone))
    except Exception as e:
        print(f"[sync] add_coach: {e}")
    return cid

def _synced_update_coach(self, cid, full_name, club="", photo_path="", bio="",
                          first_name="", last_name="", birth_date="", iin="",
                          qualification="", city="", phone="", club_id=None):
    _original_update_coach(self, cid, full_name, club, photo_path, bio,
                            first_name, last_name, birth_date, iin,
                            qualification, city, phone, club_id)
    try:
        sync_manager.dispatch_async(lambda: sync_manager.on_coach_updated(
            cid, full_name, club, photo_path, bio,
            first_name=first_name, last_name=last_name, birth_date=birth_date,
            iin=iin, qualification=qualification, city=city, phone=phone))
    except Exception as e:
        print(f"[sync] update_coach: {e}")

def _synced_set_coach_hidden(self, cid, hidden):
    _original_set_coach_hidden(self, cid, hidden)
    try:
        card = self.get_coach(cid)
        if card is None:
            return
        sync_manager.dispatch_async(lambda: sync_manager.on_coach_updated(
            cid, card["full_name"], card["club"], card["photo_path"], card["bio"],
            first_name=card["first_name"], last_name=card["last_name"],
            birth_date=card["birth_date"], iin=card["iin"],
            qualification=card["qualification"], city=card["city"],
            phone=card["phone"], is_hidden=bool(hidden)))
    except Exception as e:
        print(f"[sync] set_coach_hidden: {e}")

def _synced_delete_coach(self, cid):
    _original_delete_coach(self, cid)
    try:
        sync_manager.dispatch_async(lambda: sync_manager.on_coach_deleted(cid))
    except Exception as e:
        print(f"[sync] delete_coach: {e}")

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
    # Фото участника может быть отдельной загрузкой под турнир (папка
    # competitions/...) ИЛИ копией аватарки спортсмена (photo_path_var
    # наследуется из a["photo_path"] при выборе спортсмена). Удалять из
    # Cloudinary можно ТОЛЬКО первое — второй случай убьёт аватарку
    # спортсмена на сайте. Собираем URL до удаления строки из БД.
    photo_url = None
    try:
        row = self.get_participant(pid)
        if row and row["photo_path"]:
            pp = row["photo_path"]
            is_athlete_avatar = False
            if row["athlete_id"]:
                athlete = self.get_athlete(row["athlete_id"])
                if athlete and athlete["photo_path"] == pp:
                    is_athlete_avatar = True
            if not is_athlete_avatar:
                photo_url = pp
    except Exception as e:
        print(f"[sync] delete_participant: не удалось собрать фото участника: {e}")
        photo_url = None
    _original_delete_participant(self, pid)
    try:
        sync_manager.on_participant_deleted(pid, photo_url)
    except Exception as e:
        print(f"[sync] delete_participant: {e}")

def _synced_delete_athlete(self, aid):
    _original_delete_athlete(self, aid)
    try:
        sync_manager.dispatch_async(lambda: sync_manager.on_athlete_deleted(aid))
    except Exception as e:
        print(f"[sync] delete_athlete: {e}")

def _synced_add_club(self, name, city="", address="", founded_year=None, logo_path="", phone=""):
    cid = _original_add_club(self, name, city, address, founded_year, logo_path, phone)
    try:
        founded_date = _founded_date(founded_year)
        sync_manager.dispatch_async(lambda: sync_manager.on_club_created(
            cid, name, city=city, address=address, founded_date=founded_date,
            logo_path=logo_path, phone=phone))
    except Exception as e:
        print(f"[sync] add_club: {e}")
    return cid

def _synced_update_club(self, cid, name, city="", address="", founded_year=None, logo_path="", phone=""):
    _original_update_club(self, cid, name, city, address, founded_year, logo_path, phone)
    try:
        founded_date = _founded_date(founded_year)
        sync_manager.dispatch_async(lambda: sync_manager.on_club_updated(
            cid, name, city=city, address=address, founded_date=founded_date,
            logo_path=logo_path, phone=phone))
    except Exception as e:
        print(f"[sync] update_club: {e}")

def _founded_date(founded_year):
    """Год основания (int, как в локальном реестре) → дата для сервера."""
    if not founded_year:
        return None
    try:
        return f"{int(founded_year)}-01-01"
    except (TypeError, ValueError):
        return None

def _synced_delete_club(self, cid):
    _original_delete_club(self, cid)
    try:
        sync_manager.dispatch_async(lambda: sync_manager.on_club_deleted(cid))
    except Exception as e:
        print(f"[sync] delete_club: {e}")

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
Database.add_coach = _synced_add_coach
Database.update_coach = _synced_update_coach
Database.delete_coach = _synced_delete_coach
Database.delete_athlete = _synced_delete_athlete
Database.set_athlete_hidden = _synced_set_athlete_hidden
Database.set_coach_hidden = _synced_set_coach_hidden
Database.add_club = _synced_add_club
Database.update_club = _synced_update_club
Database.delete_club = _synced_delete_club


# ════
#  ГЕНЕРАТОР БЕЙДЖИКОВ С ШТРИХКОДАМИ
# ════

class BadgeGenerator:
    """Генерирует PDF с бейджиками участников (6 шт на A4, сетка 2×3).

    Один бейджик — один спортсмен: если человек зарегистрирован в двух
    категориях, обе показываются в таблице Left/Right на одном бейджике.
    """

    BADGE_W = 9.1 * cm
    BADGE_H = 8.75 * cm
    COLS = 2
    ROWS = 3
    MARGIN_LEFT = 1.3 * cm
    MARGIN_TOP = 1.5 * cm
    GAP_X = 0.2 * cm
    GAP_Y = 0.2 * cm

    # Логотип города Атырау — всегда на бейджике (копия лежит рядом со скриптом)
    LOGO_PATH = str(resource_path("assets/logo-atyrau-city.png"))

    # Палитра бейджика — продолжение фирменной гаммы приложения:
    # нефтепромысловый Атырау (petrol/brass/rust).
    HEADER_COLOR = "#12363B"   # petrol — каспийская глубина
    HEADER_ACCENT = "#C9A227"  # brass — латунь манометра
    PHOTO_FRAME = "#2a4a6c"
    TEXT_MAIN = "#111111"
    TEXT_DIM = "#555555"
    INFO_BLUE = "#336699"
    FOOTER_BG = "#eef1f5"
    FOOTER_BORDER = "#d5dae0"
    PLACEHOLDER_BG = "#e8edf1"
    PLACEHOLDER_TEXT = "#8a939b"
    TABLE_HEADER_BG = "#12363B"
    TABLE_GRID = "#c8cdd3"

    @staticmethod
    def generate(filepath, tournament, participants, categories_map):
        """
        Генерирует PDF с бейджиками (4 шт на лист A4). Возвращает число
        выведенных бейджиков (по одному на спортсмена).
        participants: список dict-подобных объектов (sqlite3.Row)
        categories_map: {category_id: category_name}
        """
        if not REPORTLAB_AVAILABLE:
            raise RuntimeError("Установите reportlab: pip install reportlab")

        c = pdf_canvas.Canvas(filepath, pagesize=A4)
        page_w, page_h = A4

        persons = BadgeGenerator._group_participants(participants)
        badge_idx = 0
        total = len(persons)

        for i, person in enumerate(persons):
            col = badge_idx % BadgeGenerator.COLS
            row = (badge_idx // BadgeGenerator.COLS) % BadgeGenerator.ROWS

            x = BadgeGenerator.MARGIN_LEFT + col * (BadgeGenerator.BADGE_W + BadgeGenerator.GAP_X)
            y = page_h - BadgeGenerator.MARGIN_TOP - (row + 1) * BadgeGenerator.BADGE_H - row * BadgeGenerator.GAP_Y

            BadgeGenerator._draw_badge(c, x, y, person, tournament, categories_map)

            badge_idx += 1
            if badge_idx % (BadgeGenerator.COLS * BadgeGenerator.ROWS) == 0 and i < total - 1:
                c.showPage()
                badge_idx = 0

        c.save()
        return total

    @staticmethod
    def _group_participants(participants):
        """Группирует строки-регистрации по спортсмену: один бейджик на человека."""
        groups = OrderedDict()
        for p in participants:
            key = p["athlete_id"] if p["athlete_id"] else ("anon", p["name"])
            groups.setdefault(key, []).append(p)
        return list(groups.values())

    @staticmethod
    def _age_abbrev(name):
        """Сокращение возрастной группы: Sub-Junior→SJ, Junior→J,
        Youth→YM, Senior→S, Absolute→A. Для девочек те же буквы."""
        a = str(name or "").lower().replace("-", " ")
        if "sub" in a and "junior" in a:
            return "SJ"
        if "junior" in a:
            return "J"
        if "youth" in a:
            return "YM"
        if "senior" in a:
            return "S"
        if "absolute" in a:
            return "A"
        return ""

    @staticmethod
    def _category_label(cat_name, age_category):
        """Метка категории вида 'J70', 'S75', 'S110+', 'A' (абсолютка).

        Возрастная группа определяется в первую очередь по НАЗВАНИЮ
        категории ("Junior 50kg Обе" → J, "Senior 55kg Обе" → S): спортсмен
        может участвовать в категориях разных возрастных групп (например
        юниор 17 лет записан в Junior 50 и Senior 55), а age_category в его
        карточке участника одна — по дате рождения. age_category участника
        используется только как фолбэк для категорий без возрастного
        префикса в названии."""
        age = BadgeGenerator._age_abbrev(cat_name)
        if not age:
            age = BadgeGenerator._age_abbrev(age_category)
        m = re.search(r"(\d+\+?)\s*kg\b", str(cat_name or ""))
        if m:
            return f"{age}{m.group(1)}"
        return age or "?"

    @staticmethod
    def _initials(name):
        parts = [p for p in str(name).split() if p]
        if not parts:
            return "?"
        return "".join(p[0].upper() for p in parts[:2])

    @staticmethod
    def _photo_stream(participant, photo_w, photo_h):
        """Возвращает путь к временному PNG (центр-кроп под пропорции фото)
        либо None. Вызывающий обязан удалить файл после отрисовки.

        photo_w/photo_h — размеры в пунктах. Готовое фото не растягивается:
        сначала центр-кроп до нужных пропорций, затем LANCZOS-ресайз.
        reportlab.drawImage принимает путь на диске, а не BytesIO, поэтому
        итог сохраняем во временный файл.
        """
        if not PIL_AVAILABLE:
            return None
        try:
            photo_path = participant["photo_path"] if participant["photo_path"] else None
        except Exception:
            return None
        if not photo_path:
            return None
        try:
            local_photo = resolve_local_photo_path(photo_path)
        except Exception:
            return None
        if not local_photo:
            return None
        try:
            img = Image.open(local_photo)
            img = ImageOps.exif_transpose(img)  # уважаем поворот с камеры телефона
            src_w, src_h = img.size
            target_ratio = photo_w / photo_h
            src_ratio = src_w / src_h
            if src_ratio > target_ratio:
                new_w = int(src_h * target_ratio)
                left = (src_w - new_w) // 2
                img = img.crop((left, 0, left + new_w, src_h))
            else:
                new_h = int(src_w / target_ratio)
                top = (src_h - new_h) // 2
                img = img.crop((0, top, src_w, top + new_h))
            img = img.resize((max(1, int(photo_w / 0.25)), max(1, int(photo_h / 0.25))), Image.LANCZOS)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.write(buf.getvalue())
            tmp.close()
            return tmp.name
        except Exception as e:
            print(f"[badges] фото недоступно ({photo_path}): {e}")
            return None

    @staticmethod
    def _draw_category_table(c, tx, top, rows, tw):
        """Таблица категорий Left/Right в области (tx..tx+tw), привязана к верху
        top и растёт вниз. rows: [(label, left_bool, right_bool)].

        Таблица всегда рисует минимум 2 строки: пустая ячейка показывается
        «--», а категория вписывается вместо «--» в те руки, где участвует
        спортсмен. Между колонками — «|»."""
        S = BadgeGenerator
        header_h = 0.32 * cm
        cat_h = 0.36 * cm
        if len(rows) < 2:
            rows = list(rows) + [("", False, False)] * (2 - len(rows))
        table_h = header_h + len(rows) * cat_h
        col_w = tw / 2
        pipe_color = colors.HexColor("#66737a")

        # Шапка таблицы (petrol)
        c.setFillColor(colors.HexColor(S.TABLE_HEADER_BG))
        c.roundRect(tx, top - header_h, tw, header_h, 5, fill=1, stroke=0)
        c.rect(tx, top - header_h, tw, header_h / 2, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Arial-Bold", 6.5)
        c.drawCentredString(tx + col_w / 2, top - header_h / 2 - 0.06 * cm, "Left")
        c.drawCentredString(tx + col_w * 1.5, top - header_h / 2 - 0.06 * cm, "Right")

        def _row_rect(ry, rh):
            c.setFillColor(colors.HexColor(S.FOOTER_BG))
            c.roundRect(tx, ry, tw, rh, 4, fill=1, stroke=0)
            c.rect(tx, ry + rh * 0.4, tw, rh * 0.6, fill=1, stroke=0)

        # Строки категорий
        for i, (label, left, right) in enumerate(rows):
            ry = top - header_h - (i + 1) * cat_h
            _row_rect(ry, cat_h)
            c.setFillColor(colors.HexColor(S.TEXT_MAIN))
            c.setFont("Arial-Bold", 9.5)
            c.drawCentredString(tx + col_w / 2, ry + cat_h / 2 - 0.08 * cm, label if left else "--")
            c.drawCentredString(tx + col_w * 1.5, ry + cat_h / 2 - 0.08 * cm, label if right else "--")
            c.setFillColor(pipe_color)
            c.drawCentredString(tx + col_w, ry + cat_h / 2 - 0.08 * cm, "|")

        # Сетка поверх
        c.setStrokeColor(colors.HexColor(S.TABLE_GRID))
        c.setLineWidth(0.8)
        c.roundRect(tx, top - table_h, tw, table_h, 5, fill=0, stroke=1)
        c.line(tx, top - header_h, tx + tw, top - header_h)
        for i in range(1, len(rows)):
            yy = top - header_h - i * cat_h
            c.line(tx, yy, tx + tw, yy)

    @staticmethod
    def _draw_badge(c, x, y, person, tournament, categories_map):
        bw = BadgeGenerator.BADGE_W
        bh = BadgeGenerator.BADGE_H
        S = BadgeGenerator
        participant = person[0]

        # ── 1. Белая основа с рамкой ──
        c.setStrokeColor(colors.HexColor(S.PHOTO_FRAME))
        c.setLineWidth(1.4)
        c.setFillColor(colors.white)
        c.roundRect(x, y, bw, bh, 10, fill=1, stroke=1)

        # ── 2. Шапка турнира + логотип города ──
        header_h = 1.6 * cm
        c.setFillColor(colors.HexColor(S.HEADER_COLOR))
        c.roundRect(x, y + bh - header_h, bw, header_h, 10, fill=1, stroke=0)
        # Закрываем нижние скругления шапки
        c.rect(x, y + bh - header_h, bw, 0.4 * cm, fill=1, stroke=0)
        # Латунная линия-акцент под шапкой
        c.setFillColor(colors.HexColor(S.HEADER_ACCENT))
        c.rect(x, y + bh - header_h - 0.10 * cm, bw, 0.10 * cm, fill=1, stroke=0)

        logo_drawn = False
        if os.path.exists(S.LOGO_PATH):
            try:
                logo_w = 1.1 * cm
                logo_h = 1.1 * cm
                c.drawImage(S.LOGO_PATH, x + 0.3 * cm, y + bh - 0.3 * cm - logo_h,
                            logo_w, logo_h, mask="auto")
                logo_drawn = True
            except Exception as e:
                print(f"[badges] логотип не отрисован: {e}")

        # Название турнира (со сдвигом вправо, чтобы не наезжало на логотип)
        t_name = str(tournament["name"])[:44] if tournament else "Турнир"
        name_cx = x + bw / 2 + (0.3 * cm if logo_drawn else 0)
        c.setFillColor(colors.white)
        c.setFont("Arial-Bold", 10)
        if len(t_name) > 40:
            c.setFont("Arial-Bold", 8.5)
        c.drawCentredString(name_cx, y + bh - 1.05 * cm, t_name)

        t_date = str(tournament["date"]) if tournament else ""
        if t_date:
            c.setFont("Arial", 8)
            c.setFillColor(colors.HexColor("#b7c2c7"))
            c.drawCentredString(name_cx, y + bh - 1.42 * cm, t_date)

        # ── 3. Зона имени (на всю ширину, под шапкой) ──
        name = str(participant["name"])
        body_top = y + bh - 3.25 * cm          # верх зоны фото/таблицы
        name_pt = 13
        two_lines = False
        if len(name) > 28:
            name_pt = 11
        if len(name) > 40:
            name_pt = 10
            two_lines = True
        c.setFillColor(colors.HexColor(S.TEXT_MAIN))
        c.setFont("Arial-Bold", name_pt)
        if two_lines:
            half = len(name) // 2
            split = name.rfind(" ", 0, half)
            if split <= 0:
                split = name.find(" ", half)
            if split > 0:
                c.drawCentredString(x + bw / 2, y + bh - 2.05 * cm, name[:split].strip())
                c.drawCentredString(x + bw / 2, y + bh - 2.70 * cm, name[split:].strip())
            else:
                c.drawCentredString(x + bw / 2, y + bh - 2.30 * cm, name)
        else:
            c.drawCentredString(x + bw / 2, y + bh - 2.30 * cm, name)

        # Клуб (скрывается полностью, если клуба нет)
        club = next((p["club"] for p in person if p["club"]), "")
        if club:
            c.setFillColor(colors.HexColor(S.TEXT_DIM))
            c.setFont("Arial", 8)
            c.drawCentredString(x + bw / 2, y + bh - 3.05 * cm, f"Клуб: {club}")

        # ── 4. Фото спортсмена (слева) ──
        fb_top = y + 2.3 * cm                   # верх нижней плашки
        photo_h = body_top - fb_top
        photo_w = 4.0 * cm
        px = x + 0.3 * cm
        py = fb_top

        photo_stream = BadgeGenerator._photo_stream(participant, photo_w, photo_h)
        if photo_stream is not None:
            try:
                # Скруглённое фото через clip-область
                c.saveState()
                clip_path = c.beginPath()
                clip_path.roundRect(px, py, photo_w, photo_h, 12)
                c.clipPath(clip_path, stroke=0, fill=0)
                c.drawImage(photo_stream, px, py, photo_w, photo_h, mask="auto")
                c.restoreState()
            finally:
                try:
                    os.unlink(photo_stream)
                except OSError:
                    pass
            c.setStrokeColor(colors.HexColor(S.PHOTO_FRAME))
            c.setLineWidth(1.1)
            c.roundRect(px, py, photo_w, photo_h, 12, fill=0, stroke=1)
        else:
            # Плейсхолдер: мягкая плашка + монограмма в круге
            c.setFillColor(colors.HexColor(S.PLACEHOLDER_BG))
            c.roundRect(px, py, photo_w, photo_h, 12, fill=1, stroke=0)
            cx, cy = px + photo_w / 2, py + photo_h / 2
            dia = 2.4 * cm
            c.setFillColor(colors.white)
            c.setStrokeColor(colors.HexColor("#c9d1d8"))
            c.setLineWidth(1.2)
            c.circle(cx, cy, dia / 2, fill=1, stroke=1)
            c.setFillColor(colors.HexColor(S.PLACEHOLDER_TEXT))
            c.setFont("Arial-Bold", 26)
            c.drawCentredString(cx, cy - 0.3 * cm, BadgeGenerator._initials(participant["name"]))
            c.setStrokeColor(colors.HexColor(S.PHOTO_FRAME))
            c.setLineWidth(1.1)
            c.roundRect(px, py, photo_w, photo_h, 12, fill=0, stroke=1)

        # ── 5. Таблица категорий Left/Right (справа от фото) ──
        tx = px + photo_w + 0.25 * cm
        tw = x + bw - 0.3 * cm - tx
        cat_hands = OrderedDict()
        for p in person:
            cid = p["category_id"]
            cat_hands.setdefault(cid, []).append(str(p["hand"] or ""))
        rows = []
        for cid, hands in cat_hands.items():
            # Спортсмен может участвовать в категориях РАЗНЫХ возрастных групп
            # (например Junior 50 и Senior 55) — метку каждой категории считаем
            # по age_category ИМЕННО ЭТОГО участника, а не первого в группе
            # (иначе обе строки получали бы группу первой категории: J50/J55).
            p_in_cat = next((p for p in person if p["category_id"] == cid), person[0])
            label = BadgeGenerator._category_label(categories_map.get(cid, ""), p_in_cat["age_category"])
            hs = set(hands)
            left = bool(hs & {"Обе", "Левая", "Both", "Left"})
            right = bool(hs & {"Обе", "Правая", "Both", "Right"})
            rows.append((label, left, right))
        if rows:
            BadgeGenerator._draw_category_table(c, tx, body_top, rows, tw)

        # ── 6. Нижняя плашка со штрихкодом ──
        fb_bottom = y + 0.4 * cm
        c.setFillColor(colors.HexColor(S.FOOTER_BG))
        c.roundRect(x + 0.45 * cm, fb_bottom, bw - 0.9 * cm, fb_top - fb_bottom, 8, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor(S.FOOTER_BORDER))
        c.setLineWidth(0.8)
        c.roundRect(x + 0.45 * cm, fb_bottom, bw - 0.9 * cm, fb_top - fb_bottom, 8, fill=0, stroke=1)

        barcode_value = get_barcode_value(participant["id"])
        barcode = Code128(barcode_value, barHeight=0.8 * cm, barWidth=1.0)
        barcode_width = barcode.width
        bx = x + (bw - barcode_width) / 2
        by = y + 1.02 * cm
        # Code128 рисует штрихи текущим fill-цветом — явно ставим чёрный,
        # иначе на светлой плашке штрихи сливаются с фоном.
        c.setFillColor(colors.black)
        barcode.drawOn(c, bx, by)

        # Плашка-подложка под ID-номером участника
        c.setFillColor(colors.white)
        txt_w = pdfmetrics.stringWidth(barcode_value, "Arial-Bold", 8)
        pill_w = txt_w + 0.8 * cm
        pill_h = 0.42 * cm
        pill_x = x + (bw - pill_w) / 2
        pill_y = y + 0.45 * cm
        c.roundRect(pill_x, pill_y, pill_w, pill_h, 9, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor(S.FOOTER_BORDER))
        c.setLineWidth(0.6)
        c.roundRect(pill_x, pill_y, pill_w, pill_h, 9, fill=0, stroke=1)
        c.setFillColor(colors.HexColor("#222222"))
        c.setFont("Arial-Bold", 8)
        c.drawCentredString(x + bw / 2, y + 0.6 * cm, barcode_value)

        # ── 7. Пунктирные линии для вырезания ──
        c.setStrokeColor(colors.HexColor("#cccccc"))
        c.setLineWidth(0.3)
        c.setDash(3, 3)
        c.line(x - 0.1 * cm, y, x + bw + 0.1 * cm, y)
        c.line(x - 0.1 * cm, y + bh, x + bw + 0.1 * cm, y + bh)
        c.line(x, y - 0.1 * cm, x, y + bh + 0.1 * cm)
        c.line(x + bw, y - 0.1 * cm, x + bw, y + bh + 0.1 * cm)
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
        # Сетка изменилась — это критическая операция, планируем бэкап.
        try:
            backup_manager.request_backup()
        except Exception as e:
            print(f"[backup] hook: {e}")


def _replay_bracket_results(engine, category_id, hand, results_by_slot):
    """Полностью пересчитывает сетку по зафиксированным результатам.

    results_by_slot — {match_id: 1|2} «чья сторона победила» (p1 или p2)
    для реально сыгранных матчей. Слот сохраняется, а не сам игрок: при
    изменении результата выше участники нижестоящего матча меняются,
    поэтому победителя пересчитываем по стороне сетки. Сетка сбрасывается
    к «генерационному» состоянию (участники фиксированы только в первом
    раунде WB), затем результаты проигрываются в топологическом порядке
    (по stage: winners → losers → final), как обычный прогресс турнира.
    Bye и ghost-слоты достраиваются движком.
    """
    matches = engine.db.get_matches(category_id, hand)
    bkey = lambda m: (m["stage"], {"winners": 0, "losers": 1, "final": 2}.get(m["bracket"], 3), m["match_order"])

    # 1) Сброс к состоянию сразу после генерации.
    #    Структурные ghost-матчи (done, оба слота пусты — результат
    #    _collapse_chained_byes) не трогаем: их ломать незачем.
    for m in sorted(matches, key=bkey):
        if m["status"] == "done" and not m["p1_id"] and not m["p2_id"]:
            continue
        if m["bracket"] == "winners" and m["stage"] == 0:
            engine.db.conn.execute(
                "UPDATE matches SET winner_id=NULL, p1_losses=0, p2_losses=0, "
                "status=CASE WHEN p1_id IS NOT NULL AND p2_id IS NOT NULL "
                "THEN 'pending' ELSE 'waiting' END WHERE id=?",
                (m["id"],))
        else:
            engine.db.conn.execute(
                "UPDATE matches SET p1_id=NULL, p2_id=NULL, winner_id=NULL, "
                "p1_losses=0, p2_losses=0, status='waiting' WHERE id=?",
                (m["id"],))
    engine.db.conn.commit()

    # 2) Проигрываем результаты в топологическом порядке.
    for m in sorted(matches, key=bkey):
        slot = results_by_slot.get(m["id"])
        if slot is None:
            continue
        live = engine._get_match(m["id"])
        if not live or not live["p1_id"] or not live["p2_id"]:
            # Bye/ghost-слот либо матч, который движок уже решил иначе
            # (напр. супер-финал не понадобился) — результат выставит шаг 3.
            continue
        wid = live["p1_id"] if slot == 1 else live["p2_id"]
        engine.advance_winner(m["id"], wid)

    # 3) Добиваем остатки (ghost'ы, оставшиеся bye и каскад).
    engine._resolve_all_byes(category_id, hand)


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

    def _sync_bracket_reset(self, category_id, hand):
        """clear_matches ниже удаляет старые матчи только локально —
        без этого на сайте остаются висеть прежние пары и дублируются
        с новосгенерированными в живой очереди. Снимаем список id ДО
        удаления и просим sync_manager убрать их и на сервере."""
        try:
            local_mids = [m["id"] for m in self.db.get_matches(category_id, hand)]
            sync_manager.on_bracket_reset(category_id, hand, local_mids)
        except Exception as e:
            print(f"[sync] _sync_bracket_reset: {e}")

    def _generate_bracket_impl(self, tournament_id, category_id, hand, participant_ids):
        self._sync_bracket_reset(category_id, hand)
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
                    "status": "pending" if m["p1_id"] is not None and m["p2_id"] is not None else "waiting",
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

    def _sync_match(self, match_id):
        """Двигатель сетки пишет в matches напрямую через SQL (в обход
        Database.save_match), поэтому обёртка _synced_save_match не видит
        эти изменения и на сайт ничего не летит — очередь/табло замирают.
        Дёргаем sync_manager вручную после каждого изменения матча."""
        try:
            m = self._get_match(match_id)
            if m:
                # Неблокирующая отправка: сама сетевая синхронизация уходит
                # в фоновый воркер sync_manager'а, клик по победителю не
                # ждёт HTTP-ответа (см. SyncManager.dispatch_match_update_async).
                sync_manager.dispatch_match_update_async(match_id, dict(m))
        except Exception as e:
            print(f"[sync] _sync_match({match_id}): {e}")

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
        self._sync_match(match_id)

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
                self._sync_match(match_id)
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
                        self._sync_match(m["id"])
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
        self._sync_match(match_id)

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
                    self._sync_match(gf2["id"])
            else:
                # Непобеждённый выиграл — турнир завершён, переигровка не нужна
                gf2 = self._get_match(m["win_next_id"])
                if gf2 and gf2["status"] not in ("done", "bye"):
                    self.db.conn.execute(
                        "UPDATE matches SET status='bye' WHERE id=?", (gf2["id"],))
                    self.db.conn.commit()
                    self._sync_match(gf2["id"])
            return

        if m["bracket"] == "final" and "переигровка" in m["round_name"]:
            return

        self._propagate(match_id, winner_id, loser_id)
        self._resolve_all_byes(m["category_id"], m["hand"])

    def change_winner(self, match_id, new_winner_id):
        """Пересматривает победителя уже сыгранного матча.

        Собирает зафиксированные результаты всей сетки (по стороне —
        кто выиграл пару), подменяет победителя указанного матча и
        полностью пересчитывает сетку до конца. Возвращает True при
        успехе (новый победитель — участник матча).
        """
        m = self._get_match(match_id)
        if not m or m["status"] != "done":
            return False
        if new_winner_id not in (m["p1_id"], m["p2_id"]):
            return False

        by_slot = {}
        for mm in self.db.get_matches(m["category_id"], m["hand"]):
            if mm["p1_id"] and mm["p2_id"] and mm["winner_id"] and mm["status"] == "done":
                by_slot[mm["id"]] = 1 if mm["winner_id"] == mm["p1_id"] else 2
        by_slot[match_id] = 1 if new_winner_id == m["p1_id"] else 2
        _replay_bracket_results(self, m["category_id"], m["hand"], by_slot)
        return True

    # ──── ТЕКУЩИЙ / СЛЕДУЮЩИЙ МАТЧ ────
    def get_current_and_next_match(self, category_id, hand):
        matches = self.db.get_matches(category_id, hand)

        # Текущий: первый pending-матч где известны оба участника
        ready = [m for m in matches
                 if m["status"] == "pending" and m["p1_id"] and m["p2_id"]]
        ready.sort(key=lambda m: (m["stage"], m["id"]))
        current = ready[0] if ready else None

        # Следующий: структурно следующий матч в сетке после текущего
        # (даже если участники ещё не назначены — покажем «— ожидание —»)
        if current:
            remaining = [m for m in matches
                         if m["id"] != current["id"]
                         and m["status"] not in ("done", "bye")]
            remaining.sort(key=lambda m: (m["stage"], m["id"]))
            nxt = remaining[0] if remaining else None
        else:
            remaining = [m for m in matches
                         if m["status"] not in ("done", "bye")]
            remaining.sort(key=lambda m: (m["stage"], m["id"]))
            current = remaining[0] if remaining else None
            nxt = remaining[1] if remaining and len(remaining) > 1 else None

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

        def _fighter_html(tnum, slot, fighter, name_size, photo_size):
            """Один боец: имя (без фото — на табло оно не нужно)."""
            if not fighter:
                return (f'<div class="fighter">'
                        f'<div class="fighter-name" style="font-size:{name_size}px">?</div></div>')
            name = fighter.get("name") or "?"
            return (f'<div class="fighter">'
                    f'<div class="fighter-name" style="font-size:{name_size}px">{name}</div></div>')

        def _match_html(tnum, prefix, match_data, sizes):
            """Поединок: два бойца с 'VS' между ними."""
            if not match_data:
                return ""
            p1 = _fighter_html(tnum, prefix + "1", match_data.get("p1"), sizes["name"], 0)
            p2 = _fighter_html(tnum, prefix + "2", match_data.get("p2"), sizes["name"], 0)
            return (f'<div class="match">{p1}'
                    f'<div class="vs" style="font-size:{sizes["vs"]}px">VS</div>'
                    f'{p2}</div>')

        def _render_table_block(tnum, data, sizes, cols=1):
            cat = data.get("category", "")
            # "Senior Men 55kg Both" -> "Senior Men 55kg Двоеборье"
            cat = cat.replace(" Both", " Двоеборье").replace("Both", "Двоеборье")
            hand = data.get("hand", "")
            finished = bool(data.get("finished"))
            eliminated = data.get("eliminated") or []

            # Завершённая сетка: Стол, Категория, рука + итоговая таблица
            # участников по местам с очками (победы-поражения).
            if finished and eliminated:
                rows = "".join(
                    f'<div class="final-row">'
                    f'<span class="final-place">{e["place"]}.</span>'
                    f'<span class="final-name">{e["name"]}</span>'
                    f'<span class="final-rec">{e["wins"]}-{e["losses"]}</span>'
                    f'</div>' for e in eliminated)
                return f"""
                <div class="table-block">
                  <div class="table-title">СТОЛ {tnum}</div>
                  <div class="category">Категория {cat}<br>{hand} рука</div>
                  <div class="final-list">{rows}</div>
                </div>"""

            if isinstance(current_data := data.get("current_match"), dict) and current_data.get("p1"):
                cur_html = _match_html(tnum, "c", current_data, sizes["cur"])
            elif isinstance(current_data, dict) and current_data.get("message"):
                cur_html = (f'<div class="current" '
                            f'style="font-size:{sizes["cur"]["name"]}px">{current_data["message"]}</div>')
            else:
                cur_html = (f'<div class="current" '
                            f'style="font-size:{sizes["cur"]["name"]}px">Нет активного поединка</div>')

            nxt = data.get("next_match")
            if isinstance(nxt, dict) and nxt.get("p1"):
                nxt_html = _match_html(tnum, "n", nxt, sizes["nxt"])
            elif isinstance(nxt, dict) and nxt.get("message"):
                nxt_html = (f'<div class="next" '
                            f'style="font-size:{sizes["nxt"]["name"]}px">{nxt["message"]}</div>')
            else:
                nxt_html = '<div class="next">—</div>'

            elim_html = ""
            if eliminated:
                elim_size = "12px" if cols == 2 else "18px"
                rows = "".join(
                    f'<div class="elim-row" style="font-size:{elim_size}">'
                    f'<span class="elim-place">{e["place"]}.</span>'
                    f'<span class="elim-name">{e["name"]}</span>'
                    f'<span class="elim-rec">{e["wins"]}-{e["losses"]}</span>'
                    f'</div>' for e in eliminated)
                elim_html = f'<div class="elim-title" style="font-size:{"16px" if cols == 2 else "22px"}">Выбыли</div><div class="elim-list">{rows}</div>'

            return f"""
            <div class="table-block">
              <div class="table-title">СТОЛ {tnum}</div>
              <div class="category">Категория {cat}<br>{hand} рука</div>
              <div class="current-wrap">{cur_html}</div>
              <div class="next-title">Следующий бой</div>
              <div class="next-wrap">{nxt_html}</div>
              {elim_html}
            </div>"""

        @self.app.route("/")
        def home():
            active = dict(self.tables)
            n = len(active)
            cols = min(n, 2) if n > 0 else 1

            blocks = ""
            sizes = {
                "cur": {"name": 40, "vs": 40} if cols == 2 else {"name": 56, "vs": 56},
                "nxt": {"name": 22, "vs": 34} if cols == 2 else {"name": 30, "vs": 46},
            }
            for tnum in sorted(active.keys()):
                blocks += _render_table_block(tnum, active[tnum], sizes, cols)

            if n == 0:
                blocks = "<div class='table-block'><div class='table-title'>Нет активных столов</div></div>"
                cols = 1

            title_size = "36px" if cols == 2 else "50px"
            cat_size = "22px" if cols == 2 else "32px"
            next_title_size = "24px" if cols == 2 else "36px"

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
.current-wrap {{ width: 100%; }}
.current {{
  font-weight: bold;
  color: white;
  line-height: 1.2;
}}
.next-title {{
  font-size: {next_title_size};
  color: #ffaa00;
  margin-top: 14px;
  font-weight: bold;
}}
.next-wrap {{ width: 100%; }}
.next {{
  font-size: 28px;
  color: #dddddd;
}}
.match {{
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 28px;
  flex-wrap: wrap;
  padding: 8px 0;
}}
.fighter {{
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}}
.fighter-name {{
  font-weight: bold;
  color: white;
}}
.vs {{
  color: #ffaa00;
  font-weight: bold;
}}
.elim-title {{
  font-size: 22px;
  color: #ffaa00;
  margin-top: 14px;
  font-weight: bold;
}}
.elim-list {{
  width: 100%;
  margin-top: 6px;
}}
.elim-row {{
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 2px 0;
}}
.elim-place {{
  width: 34px;
  text-align: right;
  color: #8899aa;
  flex-shrink: 0;
}}
.elim-name {{
  color: #dddddd;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
.elim-rec {{
  margin-left: auto;
  color: #556677;
  flex-shrink: 0;
}}
.final-list {{
  width: 100%;
  margin-top: 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}}
.final-row {{
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 8px;
  border-radius: 8px;
  background: #16202e;
  font-size: 20px;
}}
.final-place {{
  width: 40px;
  text-align: right;
  color: #00ff88;
  font-weight: bold;
  flex-shrink: 0;
}}
.final-name {{
  color: white;
  font-weight: bold;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
.final-rec {{
  margin-left: auto;
  color: #8899aa;
  font-weight: bold;
  flex-shrink: 0;
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
<div class="footer">Турнирная система: Double Elimination (до 2 поражений) · build {DisplayServer._build_tag()}</div>
</body>
</html>"""

        @self.app.route("/diag")
        def diag():
            """Диагностика: какой код обслуживает табло и какие фото переданы."""
            out = {"build": DisplayServer._build_tag(), "tables": {}}
            for tnum, d in self.tables.items():
                def row(holder):
                    if not isinstance(holder, dict):
                        return None
                    if holder.get("message"):
                        return {"message": holder["message"]}
                    r = {}
                    for k in ("p1", "p2"):
                        f = holder.get(k) or {}
                        r[k] = {"name": f.get("name"), "photo": f.get("photo")}
                    return r
                out["tables"][tnum] = {
                    "category": d.get("category"),
                    "hand": d.get("hand"),
                    "current": row(d.get("current_match")),
                    "next": row(d.get("next_match")),
                }
            from flask import jsonify
            return jsonify(out)

    def update_table(self, table_num, category, hand, current_match, next_match, eliminated=None, finished=False):
        self.tables[str(table_num)] = {
            "category": category,
            "hand": hand,
            "current_match": current_match,
            "next_match": next_match,
            "eliminated": eliminated or [],
            "finished": finished,
        }

    def remove_table(self, table_num):
        self.tables.pop(str(table_num), None)

    def start(self):
        def run():
            try:
                self.app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
            except OSError as e:
                if "address already in use" in str(e).lower() or "winerror 10048" in str(e).lower():
                    print("[display] ⚠ ПОРТ 5000 занят другой копией приложения — "
                          "табло отдаёт СТАРЫЙ процесс! Закройте все копии и запустите заново.")
                else:
                    print(f"[display] ошибка запуска табло: {e}")
        Thread(target=run, daemon=True).start()

    @staticmethod
    def _build_tag():
        return "v3-cdn"


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

        photo_label = ctk.CTkLabel(self, text="👤", font=("Arial", 28), width=92, height=112,
                    fg_color="#0d1420", corner_radius=12)
        local_photo = resolve_local_photo_path(p["photo_path"], only_cached=True) if PIL_AVAILABLE and p["photo_path"] else None
        if local_photo:
            try:
                img = load_photo_thumbnail(local_photo, 184, 224)
                photo = ctk.CTkImage(img, size=(92, 112))
                photo_label = ctk.CTkLabel(self, image=photo, text="", width=92, height=112)
                photo_label._image = photo
            except Exception:
                pass
        photo_label.grid(row=0, column=0, rowspan=3, padx=(6, 3), pady=2)

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
                    fg_color=DANGER, hover_color=DANGER_HOVER,
                    command=lambda: on_delete(p["id"])).pack(pady=2)
        self.columnconfigure(1, weight=1)

class ParticipantGroupCard(ctk.CTkFrame):
    """Одна карточка на спортсмена. Если он зарегистрирован в нескольких
    категориях этого турнира, все они показываются внутри ОДНОЙ карточки
    отдельными строками (со своим весом/хватом/штрихкодом на каждую),
    вместо того чтобы дублировать карточку целиком на каждую категорию."""

    PHOTO_W, PHOTO_H = 128, 144

    def __init__(self, master, participants, on_edit, on_delete, **kwargs):
        super().__init__(master, corner_radius=12, **kwargs)
        self.configure(fg_color=("#1e2a3a", "#1e2a3a"))
        first = participants[0]

        # ── фото — фиксированный размер, обрезаем по центру под рамку,
        #    чтобы карточки не "прыгали" от формы исходного файла ──
        photo_holder = ctk.CTkFrame(self, width=self.PHOTO_W, height=self.PHOTO_H,
                    corner_radius=8, fg_color="#0d1420")
        photo_holder.grid(row=0, column=0, rowspan=len(participants) + 1,
                          padx=(14, 10), pady=14)
        photo_holder.grid_propagate(False)
        photo_holder.columnconfigure(0, weight=1)
        photo_holder.rowconfigure(0, weight=1)

        photo_label = ctk.CTkLabel(photo_holder, text="👤",
                    font=("Arial", 30), text_color="#556677")
        # only_cached=True: карточки строятся на UI-потоке, скачивание
        # Cloudinary (до 15с на фото) зависало бы на весь список.
        local_photo = resolve_local_photo_path(first["photo_path"], only_cached=True) if PIL_AVAILABLE and first["photo_path"] else None
        if local_photo:
            try:
                img = Image.open(local_photo)
                img = ImageOps.exif_transpose(img)
                img = ImageOps.fit(img, (self.PHOTO_W * 2, self.PHOTO_H * 2), Image.LANCZOS)
                img = round_corners(img, self.PHOTO_W // 8)
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
                    fg_color=DANGER, hover_color=DANGER_HOVER,
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

    def _sync_bracket_reset(self, category_id, hand):
        """См. одноимённый метод в DoubleEliminationEngine — без него
        старые матчи остаются висеть на сайте после пересоздания сетки."""
        try:
            local_mids = [m["id"] for m in self.db.get_matches(category_id, hand)]
            sync_manager.on_bracket_reset(category_id, hand, local_mids)
        except Exception as e:
            print(f"[sync] _sync_bracket_reset: {e}")

    def _generate_bracket_impl(self, tournament_id, category_id, hand, participant_ids):
        self._sync_bracket_reset(category_id, hand)
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
                    "status": "pending" if m["p1_id"] is not None and m["p2_id"] is not None else "waiting",
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

    def _sync_match(self, match_id):
        """См. одноимённый метод в DoubleEliminationEngine: движок пишет
        матчи в обход Database.save_match, так что без ручного вызова
        синка изменения (в т.ч. результат поединка) на сайт не долетают."""
        try:
            m = self._get_match(match_id)
            if m:
                # Неблокирующая отправка: сама сетевая синхронизация уходит
                # в фоновый воркер sync_manager'а, клик по победителю не
                # ждёт HTTP-ответа (см. SyncManager.dispatch_match_update_async).
                sync_manager.dispatch_match_update_async(match_id, dict(m))
        except Exception as e:
            print(f"[sync] _sync_match({match_id}): {e}")

    def _place_player(self, match_id, slot, player_id):
        if player_id is None:
            return
        m = self._get_match(match_id)
        col = "p1_id" if slot == 1 else "p2_id"
        if col not in ("p1_id", "p2_id"):
            raise ValueError(f"Недопустимая колонка: {col}")
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
        self._resolve_if_bye(match_id)
        self._sync_match(match_id)

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
                self._sync_match(match_id)
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
        self._sync_match(match_id)

        if m["win_next_id"]:
            self._place_player(m["win_next_id"], m["win_next_slot"], winner_id)
        self._resolve_all_byes(m["category_id"], m["hand"])

    def change_winner(self, match_id, new_winner_id):
        """Пересматривает победителя уже сыгранного матча.

        Собирает зафиксированные результаты всей сетки, подменяет победителя
        указанного матча и полностью пересчитывает сетку до конца. Возвращает
        True при успехе (новый победитель — участник матча).
        """
        m = self._get_match(match_id)
        if not m or m["status"] != "done":
            return False
        if new_winner_id not in (m["p1_id"], m["p2_id"]):
            return False

        by_slot = {}
        for mm in self.db.get_matches(m["category_id"], m["hand"]):
            if mm["p1_id"] and mm["p2_id"] and mm["winner_id"] and mm["status"] == "done":
                by_slot[mm["id"]] = 1 if mm["winner_id"] == mm["p1_id"] else 2
        by_slot[match_id] = 1 if new_winner_id == m["p1_id"] else 2
        _replay_bracket_results(self, m["category_id"], m["hand"], by_slot)
        return True

    def get_current_and_next_match(self, category_id, hand):
        matches = self.db.get_matches(category_id, hand)

        ready = [m for m in matches
                 if m["status"] == "pending" and m["p1_id"] and m["p2_id"]]
        ready.sort(key=lambda m: (m["stage"], m["id"]))
        current = ready[0] if ready else None

        if current:
            remaining = [m for m in matches
                         if m["id"] != current["id"]
                         and m["status"] not in ("done", "bye")]
            remaining.sort(key=lambda m: (m["stage"], m["id"]))
            nxt = remaining[0] if remaining else None
        else:
            remaining = [m for m in matches
                         if m["status"] not in ("done", "bye")]
            remaining.sort(key=lambda m: (m["stage"], m["id"]))
            current = remaining[0] if remaining else None
            nxt = remaining[1] if remaining and len(remaining) > 1 else None

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
                    "eliminated": False, "elim_round_score": -1, "elim_order": 0}

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
                            stats[loser]["elim_order"] = m["match_order"]
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

        # Места в single elimination: выбывшие получают УНИКАЛЬНЫЕ места по
        # порядку выбывания — первый выбывший в своём раунде занимает нижнее
        # место диапазона. Для 8 участников (3 раунда):
        #   1/4 финала (stage 0) -> места 5,6,7,8
        #   полуфинал (stage 1)  -> места 3,4
        #   финал (stage 2)      -> место 2
        #   чемпион              -> место 1
        # Кто раньше проиграл в раунде (по порядку матча) — тот ниже.
        rounds = max((m["stage"] for m in matches), default=0) + 1 if matches else 0
        by_round: dict[int, list] = {}
        for s in stats.values():
            if s["eliminated"]:
                by_round.setdefault(s["elim_round_score"], []).append(s)
        occupied = set()
        for st, lst in by_round.items():
            lst.sort(key=lambda s: (s["elim_order"], s["pid"]))
            max_place = 2 ** (rounds - st)
            for i, s in enumerate(lst):
                s["place"] = max_place - i
                occupied.add(s["place"])

        for s in stats.values():
            if s["pid"] == champion:
                s["place"] = 1
                occupied.add(1)

        # Ещё не выбывшие (сетка не доиграна) — занимают оставшиеся свободные
        # места сверху вниз (по победам), не пересекаясь с выбывшими.
        not_out = [s for s in stats.values()
                   if not s["eliminated"] and s["pid"] != champion]
        not_out.sort(key=lambda s: (-s["wins"], s["pid"]))
        free_place = 1
        for s in not_out:
            while free_place in occupied:
                free_place += 1
            s["place"] = free_place
            occupied.add(free_place)

        return sorted(stats.values(), key=lambda s: s["place"])


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

    Тай-брейк при равных очках — меньший вес (после контрольного взвешивания).
    При равных очках И весе спортсмены делят одно место, если жюри не задало
    ручное место (dvoeborie_overrides.manual_rank) — тогда выбранный спортсмен
    поднимается в начало «спорной» группы и получает отдельное (более высокое)
    место, остальные в группе делят следующее.

    Возвращает список словарей, отсортированный по итоговому месту:
        pid, name, club, weight, right_place, right_points,
        left_place, left_points, total_points, place
    """
    right = _standings_with_place(engine, category["id"], "Правая")
    left = _standings_with_place(engine, category["id"], "Левая")

    right_map = {s["pid"]: s for s in right}
    left_map = {s["pid"]: s for s in left}

    overrides = {}
    try:
        overrides = db.get_dvoeborie_overrides(category["tournament_id"], category["id"])
    except Exception:
        overrides = {}

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
            "weight": p["weight"] if "weight" in p.keys() else None,
            "right_place": r_place,
            "left_place": l_place,
            "right_points": r_pts,
            "left_points": l_pts,
            "total_points": r_pts + l_pts,
        })

    def best_place(row):
        places = [x for x in (row["right_place"], row["left_place"]) if x]
        return min(places) if places else 9999

    def weight_key(w):
        return w if w is not None else float("inf")

    # Больше очков — выше; при равных очках — меньше вес; затем лучшее место
    # на какой-либо руке; иначе — по имени (стабильность порядка).
    rows.sort(key=lambda r: (-r["total_points"], weight_key(r["weight"]),
                             best_place(r), r["name"]))

    # Внутри «спорных» групп (одинаковые очки и вес) выбранный жюри
    # победитель (manual_rank) поднимается в начало группы.
    if overrides:
        ordered = []
        i = 0
        n = len(rows)
        while i < n:
            j = i
            while (j < n and rows[j]["total_points"] == rows[i]["total_points"]
                   and weight_key(rows[j]["weight"]) == weight_key(rows[i]["weight"])):
                j += 1
            group = rows[i:j]
            group.sort(key=lambda r: (overrides.get(r["pid"], 1 << 30),
                                      best_place(r), r["name"]))
            ordered.extend(group)
            i = j
        rows = ordered

    # Итоговое место: равные очки и вес делят одно место; спортсмен с
    # manual_rank внутри группы получает своё отдельное (более высокое) место.
    place = 0
    prev_key = None
    for i, row in enumerate(rows):
        key = (row["total_points"], weight_key(row["weight"]), overrides.get(row["pid"]))
        if key != prev_key:
            place = i + 1
            prev_key = key
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
        self.is_double_elimination = bracket_system != "single"
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

        # Кеш данных для ускорения отрисовки (см. _ensure_cache)
        self._match_cache = None
        self._participant_cache = {}
        self._cache_dirty = True
        self._load_bracket_timer = None

        self.title(f"Сетка — {category['name']} — {hand}")
        self.configure(fg_color=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Сетка всегда открывается на весь экран
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.after(10, self._apply_fullscreen)
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

    def _apply_fullscreen(self):
        try:
            self.state("zoomed")
        except Exception:
            try:
                self.attributes("-zoomed", True)
            except Exception:
                self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")

    def safe_init(self):
        try:
            self._build_ui()
            self._load_bracket()
            self._assign_table_number()
            self.deiconify()
            self.update_idletasks()
            # Окно сетки делаем owned (transient) к главному окну: Windows сам
            # держит его поверх родителя и показывает диалоги поверх него.
            _keep_topmost(self)
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Ошибка сетки", str(e))
            self.destroy()

    def _build_ui(self):
        top = ctk.CTkFrame(self, fg_color=PANEL, height=55)
        top.pack(fill="x", padx=0, pady=0)
        top.pack_propagate(False)

        title_text = f"🏆  {self.category['name']}  |  {self.hand}  |  До {2 if self.is_double_elimination else 1} поражения"
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
        self.bind("<FocusIn>", lambda e: self.scan_entry.focus_set() if e.widget is self else None)
        self.tabs = ctk.CTkTabview(self, fg_color=BG)
        self.tabs.pack(fill="both", expand=True, padx=5, pady=5)
        self.tabs.add("🏟 Сетка")
        self.tabs.add("📋 Поединки")
        self.tabs.add("🥇 Итоги")

        bracket_outer = self.tabs.tab("🏟 Сетка")
        self.canvas_frame = ctk.CTkFrame(bracket_outer, fg_color=BG)
        self.canvas_frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(self.canvas_frame, bg=BG,
                    highlightthickness=0, cursor="crosshair")
        hscroll = ctk.CTkScrollbar(self.canvas_frame, orientation="horizontal",
                    command=self.canvas.xview)
        vscroll = ctk.CTkScrollbar(self.canvas_frame, orientation="vertical",
                    command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hscroll.set, yscrollcommand=vscroll.set)
        hscroll.pack(side="bottom", fill="x")
        vscroll.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True)

        # Колесо мыши: вертикальный скролл, Shift+колесо — горизонтальный
        # (сетка большого турнира не помещается в окно).
        self.canvas.bind("<MouseWheel>", self._on_canvas_wheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_canvas_hwheel)
        self.canvas_frame.bind("<MouseWheel>", self._on_canvas_wheel)
        self.canvas_frame.bind("<Shift-MouseWheel>", self._on_canvas_hwheel)

        match_tab = self.tabs.tab("📋 Поединки")
        self.match_scroll = ScrollableFrame(match_tab, fg_color=BG)
        self.match_scroll.pack(fill="both", expand=True, padx=10, pady=10)

        result_tab = self.tabs.tab("🥇 Итоги")
        self.result_frame = ctk.CTkFrame(result_tab, fg_color=BG)
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
            self._invalidate_cache()
            self._load_bracket_debounced()
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
        def pdata(pid):
            """Имя + фото участника для табло."""
            if not pid:
                return {"name": "?", "photo": ""}
            p = self._participant_cache.get(pid)
            if not p:
                return {"name": "?", "photo": ""}
            return {"name": p["name"], "photo": p["photo_path"] or ""}

        current, nxt = self.engine.get_current_and_next_match(
            self.category["id"], self.hand)

        current_data = None
        if current:
            current_data = {
                "p1": pdata(current["p1_id"]),
                "p2": pdata(current["p2_id"]),
            }
            txt = (f"⚔️  {current_data['p1']['name']}  vs  {current_data['p2']['name']}")
            self.lbl_current.configure(text=txt, text_color="#4dccff")
        else:
            matches = self._match_cache
            if not matches:
                txt = "⚔️  Сетка не создана"
                self.lbl_current.configure(text=txt, text_color="#556677")
            else:
                pending_any = [m for m in matches if m["status"] == "pending"]
                if pending_any:
                    txt = "⏳  Ожидание участников для следующего поединка..."
                    self.lbl_current.configure(text=txt, text_color="#ffaa33")
                else:
                    finals = [m for m in matches if m["bracket"] == "final" and m["status"] == "done"]
                    if finals:
                        winner = pdata(finals[-1]["winner_id"])["name"]
                        txt = f"🏆  Турнир завершён! Победитель: {winner}"
                        self.lbl_current.configure(text=txt, text_color="#ffd700")
                    else:
                        txt = "✅  Все поединки завершены"
                        self.lbl_current.configure(text=txt, text_color="#4dff88")
            current_data = {"message": txt}

        next_data = None
        if nxt:
            next_data = {
                "p1": pdata(nxt["p1_id"]),
                "p2": pdata(nxt["p2_id"]),
            }
            txt_n = (f"⏭  {next_data['p1']['name']}  vs  {next_data['p2']['name']}")
            self.lbl_next.configure(text=txt_n, text_color="#aabbcc")
        else:
            txt_n = "⏭  Следующий: —"
            self.lbl_next.configure(text=txt_n, text_color="#445566")
            next_data = {"message": txt_n}

        app = self.master
        if hasattr(app, "display_server") and self.table_number is not None:
            finished = False
            if self._match_cache:
                finals = [m for m in self._match_cache
                          if m["bracket"] == "final" and m["status"] == "done"]
                pending_any = [m for m in self._match_cache if m["status"] == "pending"]
                finished = bool(finals) or (not pending_any and
                                            all(m["status"] in ("done", "bye") for m in self._match_cache))
            app.display_server.update_table(
                self.table_number,
                self.category["name"],
                self.hand,
                current_data,
                next_data,
                self._compute_eliminated(),
                finished,
            )

    def _compute_eliminated(self):
        """Выбывшие спортсмены этой категории/руки для табло — по той же
        логике, что на сайте (см. backend/app/api/v1/public/competitions.py)."""
        matches = self.db.get_matches(self.category["id"], self.hand)
        done = [m for m in matches if m["status"] == "done" and m["winner_id"]]
        if not done:
            return []

        stats = OrderedDict()

        def ensure(pid):
            if pid is not None and pid not in stats:
                stats[pid] = {"pid": pid, "wins": 0, "losses": 0,
                              "last_loss_stage": -1, "last_loss_order": 0}

        for m in done:
            ensure(m["p1_id"])
            ensure(m["p2_id"])
            winner = m["winner_id"]
            loser = m["p2_id"] if winner == m["p1_id"] else m["p1_id"]
            ensure(winner)
            stats[winner]["wins"] += 1
            if loser:
                ensure(loser)
                stats[loser]["losses"] += 1
                if m["stage"] > stats[loser]["last_loss_stage"]:
                    stats[loser]["last_loss_stage"] = m["stage"]
                    stats[loser]["last_loss_order"] = m["match_order"]

        # Чемпион — победитель последнего терминального матча (win_next_id IS NULL).
        terminal = [m for m in done if m["win_next_id"] is None]
        champion = None
        if terminal:
            last_term = max(terminal, key=lambda m: m["stage"])
            champion = last_term["winner_id"]
        gf_done = champion is not None

        max_losses = 2 if self.engine.__class__.__name__ == "DoubleEliminationEngine" else 1

        def name_of(pid):
            p = self._participant_cache.get(pid)
            return p["name"] if p else "?"

        eliminated = []
        if max_losses == 1:
            # Single elimination: уникальные места по порядку выбывания.
            all_ms = self._match_cache or matches
            ids = set()
            for m in all_ms:
                if m["p1_id"] is not None:
                    ids.add(m["p1_id"])
                if m["p2_id"] is not None:
                    ids.add(m["p2_id"])
            n_total = len(ids)
            by_round = {}
            for s in stats.values():
                if s["losses"] >= 1:
                    by_round.setdefault(s["last_loss_stage"], []).append(s)
            placed = {}
            eliminated_so_far = 0
            for st in sorted(by_round):
                lst = sorted(by_round[st], key=lambda s: (s["last_loss_order"], s["pid"]))
                max_place = n_total - eliminated_so_far
                for i, s in enumerate(lst):
                    placed[s["pid"]] = max_place - i
                eliminated_so_far += len(lst)
            if champion is not None:
                placed[champion] = 1
            ordered = [s for s in stats.values() if s["pid"] in placed]
            ordered.sort(key=lambda s: placed[s["pid"]])
            for s in ordered:
                eliminated.append({
                    "name": name_of(s["pid"]),
                    "place": placed[s["pid"]],
                    "wins": s["wins"],
                    "losses": s["losses"],
                })
        else:
            # Double elimination: чемпион первым, дальше по поражениям/победам.
            ordered = sorted(
                stats.values(),
                key=lambda s: (
                    0 if s["pid"] == champion else 1,
                    s["losses"],
                    -s["wins"],
                )
            )
            for i, s in enumerate(ordered):
                is_eliminated = gf_done or s["losses"] >= max_losses
                if is_eliminated:
                    eliminated.append({
                        "name": name_of(s["pid"]),
                        "place": i + 1,
                        "wins": s["wins"],
                        "losses": s["losses"],
                    })
        return eliminated

    def _ensure_cache(self):
        if not self._cache_dirty and self._match_cache is not None:
            return
        t0 = __import__("time").time()
        self._match_cache = self.db.get_matches(self.category["id"], self.hand)
        all_participants = self.db.get_participants_by_category(self.category["id"])
        self._participant_cache = {p["id"]: p for p in all_participants}
        self._cache_dirty = False
        dt = __import__("time").time() - t0
        if dt > 0.01:
            print(f"[perf] кеш: {len(self._match_cache)} матчей, {len(self._participant_cache)} участников за {dt:.3f}s")

    def _invalidate_cache(self):
        self._cache_dirty = True

    def _load_bracket(self):
        self._ensure_cache()
        t0 = __import__("time").time()
        self._refresh_match_info_bar()
        self._draw_bracket()
        self._render_match_list()
        self._render_results()
        dt = __import__("time").time() - t0
        if dt > 0.01:
            print(f"[perf] _load_bracket: {dt:.3f}s")

    def _load_bracket_debounced(self):
        if self._load_bracket_timer:
            self.after_cancel(self._load_bracket_timer)
        self._load_bracket_timer = self.after(250, self._load_bracket)

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
        # Защита от случайного «Создать сетку» по ходу турнира: если в сетке
        # уже есть результаты, пересоздание не разрешаем — только сброс.
        existing = self.db.get_matches(self.category["id"], self.hand)
        played = [m for m in existing if m["winner_id"] is not None]
        if played:
            messagebox.showwarning("Сетка уже идёт",
                    "В этой сетке уже есть результаты поединков.\n"
                    "Пересоздать сетку можно только через «Сбросить сетку».")
            return
        if existing:
            messagebox.showinfo("Сетка уже создана",
                    "Сетка уже создана — при повторном создании будет "
                    "повторён тот же порядок пар.\n"
                    "Чтобы получить новую случайную сетку, нажмите «Сбросить сетку».")
        elif not messagebox.askyesno("Создать сетку",
                    f"Будет создана сетка для {len(participants)} участников. Продолжить?"):
            return
        import random
        ids = [p["id"] for p in participants]
        generation = self.db.get_bracket_generation(self.category["id"], self.hand)
        # Сид включает руку и поколение сетки: левая и правая рука получают
        # РАЗНЫЙ порядок пар, а каждая пересозданная после сброса сетка —
        # новый случайный порядок.
        rng = random.Random(f"{self.tournament_id}-{self.category['id']}-{self.hand}-{generation}")
        rng.shuffle(ids)
        self.engine.generate_bracket(self.tournament_id, self.category["id"], self.hand, ids)
        self._invalidate_cache()
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
                # Неблокирующе: раньше это была последовательность из N
                # блокирующих PATCH-запросов (по одному на матч) прямо на
                # UI-потоке — открытие окна сетки/смена стола подвисали на
                # секунды при живой сети. Теперь весь цикл уезжает одной
                # задачей в фоновый воркер sync_manager'а.
                table_number = self.table_number
                sync_manager.dispatch_async(
                    lambda mids=mids, tn=table_number: sync_manager.on_matches_table_assigned(mids, tn)
                )
        except Exception as e:
            print(f"[sync] assign_table: {e}")

    def _suggest_table_number(self):
        """Первый свободный номер стола среди открытых сеток и сохранённых
        в БД трансляций других категорий (окно может быть закрыто, но стол
        из-за этого не освобождается)."""
        used = {
            w.table_number for w in getattr(self.master, "_open_bracket_windows", [])
            if w is not self and w.winfo_exists() and w.table_number is not None
        }
        used |= self.db.get_broadcast_table_numbers(
            self.tournament_id, self.category["id"], self.hand)
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
        if table_number in self.db.get_broadcast_table_numbers(
                self.tournament_id, self.category["id"], self.hand):
            return "другая категория с сохранённой трансляцией"
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
        old_number = self.table_number
        self.table_number = table_number
        self._assign_table_number()
        self._refresh_broadcast_status_label()
        # Сразу пушим/снимаем текущий матч с табло — иначе после включения
        # трансляции оно пустое до следующей перезагрузки сетки.
        try:
            if table_number is not None:
                self._refresh_match_info_bar()
            elif old_number is not None and hasattr(self.master, "display_server"):
                self.master.display_server.remove_table(old_number)
        except Exception as e:
            print(f"[display] apply broadcast: {e}")

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
                # Автоподбор номера стола без диалога: если этот номер уже
                # транслируется другой открытой сеткой (стол 1 занят первой
                # сеткой), сразу берём следующий свободный (стол 2, 3, ...).
                table_num = self.table_number
                if table_num is None:
                    table_num = self._suggest_table_number()
                elif self._find_broadcast_conflict(table_num):
                    suggested = self._suggest_table_number()
                    if suggested != table_num:
                        table_num = suggested
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
        try:
            local_mids = [m["id"] for m in self.db.get_matches(self.category["id"], self.hand)]
            sync_manager.on_bracket_reset(self.category["id"], self.hand, local_mids)
        except Exception as e:
            print(f"[sync] _reset_bracket: {e}")
        self.db.clear_matches(self.category["id"], self.hand)
        self.db.bump_bracket_generation(self.category["id"], self.hand)
        self._invalidate_cache()
        self._load_bracket()
        messagebox.showinfo("Готово", "Сетка сброшена.", parent=self)

    # ────
    @staticmethod
    def _build_stage_labels(w_round_names, l_round_names):
        """Определяет подписи «Полуфинал» / «Финал» для колонок сетки.

        Double elimination:
          - Последний раунд WB (Финал WB) → Полуфинал
          - Последний раунд LB (Финал LB) → Полуфинал
          - Сам финал (Гранд-финал) подписывается отдельно в _draw_bracket

        Single elimination:
          - Последний раунд → Финал
          - Предпоследний → Полуфинал
        """
        labels = {}
        has_lb = len(l_round_names) > 0

        if w_round_names:
            labels[("winners", w_round_names[-1])] = "Полуфинал" if has_lb else "Финал"
            if not has_lb and len(w_round_names) >= 2:
                labels[("winners", w_round_names[-2])] = "Полуфинал"

        if has_lb and l_round_names:
            labels[("losers", l_round_names[-1])] = "Полуфинал"

        return labels

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

        # Нерисуемые «сервисные» матчи:
        #  - ghost-слоты «BYE vs BYE» (оба участника пустые);
        #  - bye-матчи НЕ первого раунда своей секции (полуфинальные, в нижней
        #    сетке и т.п.) — они появляются при переносе bye глубже в сетку.
        #  А вот первый раунд при нечётном числе участников показываем честной
        #  парой «участник / BYE», как и положено в турнирной сетке.
        by_id = {m["id"]: m for m in matches}
        first_stage = {}
        for m in matches:
            bs = m["bracket"]
            first_stage[bs] = min(first_stage.get(bs, m["stage"]), m["stage"])
        ghost_ids = {
            m["id"] for m in matches
            if m["is_bye"] == 1 and (
                (m["p1_id"] is None and m["p2_id"] is None)
                or (m["p2_id"] is None and m["stage"] != first_stage.get(m["bracket"], m["stage"]))
            )
        }

        def visible_rounds(src_rounds):
            out = OrderedDict()
            for rname, rmatches in src_rounds.items():
                kept = [m for m in rmatches if m["id"] not in ghost_ids]
                if kept:
                    out[rname] = kept
            return out

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

        # Колонки без единого видимого матча (все слоты — ghost/byes) выкидываем,
        # чтобы не оставалось пустых вертикалей между реальными раундами.
        w_rounds = visible_rounds(w_rounds)
        l_rounds = visible_rounds(l_rounds)
        f_rounds = visible_rounds(f_rounds)

        # Крупнее карточки и больше воздуха между колонками/строками —
        # так надписи не наезжают друг на друга и сетка выглядит аккуратнее.
        BOX_W, BOX_H = 250, 72
        H_GAP = 64
        SLOT_H = BOX_H + 22
        X_START = 24
        HEADER_H = 34          # место под заголовок колонки над первой карточкой
        Y_W_START = 24 + HEADER_H

        w_rounds_list = list(w_rounds.items())
        if not w_rounds_list:
            return

        w_round_names = list(w_rounds.keys())
        l_round_names = list(l_rounds.keys())
        stage_labels = self._build_stage_labels(w_round_names, l_round_names)

        def y_pos(match_idx, round_idx):
            step = SLOT_H * (2 ** round_idx)
            first_center = Y_W_START + (SLOT_H * (2 ** round_idx) - BOX_H) / 2
            return first_center + match_idx * step

        # Сначала только вычисляем координаты всех боксов (не рисуем) — потом
        # по ним строим стрелки, и уже поверх стрелок рисуем сами карточки.
        # Так длинные стрелки «ныряют» под карточками, а не пробивают их.
        box_pos = {}       # match_id -> (x, y)
        box_defs = []      # (match, x, y, highlight)
        text_defs = []     # (x, y, text, fill, font, anchor)
        max_y_w = Y_W_START

        for ri, (rname, rmatches) in enumerate(w_rounds_list):
            x = X_START + ri * (BOX_W + H_GAP)
            for mi, m in enumerate(rmatches):
                y = y_pos(mi, ri)
                box_pos[m["id"]] = (x, y)
                box_defs.append((m, x, y, None))
                max_y_w = max(max_y_w, y + BOX_H)
            label = stage_labels.get(("winners", rname))
            if label:
                text_defs.append(
                    (x + BOX_W / 2, Y_W_START - HEADER_H / 2, label, "#7fb8ff",
                     ("Arial", 15, "bold"), "c"))

        x_final = X_START + len(w_rounds_list) * (BOX_W + H_GAP)
        y_final = Y_W_START
        for fi, (rname, rmatches) in enumerate(f_rounds.items()):
            x_this = x_final + fi * (BOX_W + H_GAP)   # ← сдвиг вправо вместо вниз
            is_reset_round = "переигровка" in rname
            visible_matches = [
                m for m in rmatches
                if not (is_reset_round and not (m["p1_id"] and m["p2_id"]) and m["status"] != "done")
            ]
            if visible_matches:
                # Первый матч финала — «Финал», переигровка — «Гранд-финал».
                label = "Гранд-финал" if is_reset_round else "Финал"
                text_defs.append(
                    (x_this + BOX_W / 2, Y_W_START - HEADER_H / 2, label, "#ffcc66",
                     ("Arial", 15, "bold"), "c"))
            for m in visible_matches:
                box_pos[m["id"]] = (x_this, y_final)
                box_defs.append((m, x_this, y_final, "#3a3010"))
                max_y_w = max(max_y_w, y_final + BOX_H)

        Y_L_START = max_y_w + 80
        l_rounds_list = list(l_rounds.values())
        for ri, rmatches in enumerate(l_rounds_list):
            x = X_START + (ri + 1) * (BOX_W + H_GAP)
            # Шаг растёт вдвое каждые два раунда (после объединяющих раундов)
            step_mult = 2 ** (ri // 2)
            step = SLOT_H * step_mult
            # Центрируем первый матч относительно всей высоты первого раунда
            total_first = SLOT_H * max(len(l_rounds_list[0]), 1)
            first_offset = (step - SLOT_H) // 2
            col_ys = []
            for mi, m in enumerate(rmatches):
                y = Y_L_START + first_offset + mi * step
                box_pos[m["id"]] = (x, y)
                box_defs.append((m, x, y, "#2a1510"))
                col_ys.append(y)
            label = stage_labels.get(("losers", l_round_names[ri]))
            if label and col_ys:
                text_defs.append(
                    (x + BOX_W / 2, min(col_ys) - 18, label, "#ff9955",
                     ("Arial", 14, "bold"), "c"))

        # ── Стрелки ──
        # Рисуем строго по ссылкам win_next_id / lose_next_id (а не по позициям
        # match_order): сквозь ghost-слоты цепочка перепрыгивает на следующий
        # видимый матч, а связки «верхняя → нижняя сетка» и «нижняя → финал»
        # больше не теряются. Линии цветим по тому, куда ведёт стрелка.
        LINE_COLORS = {"winners": "#2a4a6a", "losers": "#7a3a1a", "final": "#8a6a10"}

        def resolve_next(match, kind):
            nid = match["win_next_id"] if kind == "win" else match["lose_next_id"]
            steps = 0
            while nid is not None and nid not in box_pos and steps < 64:
                n = by_id.get(nid)
                if n is None:
                    nid = None
                    break
                nid = n["win_next_id"]
                steps += 1
            return nid

        for mid in list(box_pos):
            m = by_id[mid]
            for kind in ("win", "lose"):
                if kind == "lose" and m["bracket"] == "winners":
                    # стрелки из верхней сетки в нижнюю не рисуем
                    continue
                tid = resolve_next(m, kind)
                if tid is None or tid not in box_pos:
                    continue
                x1 = box_pos[mid][0] + BOX_W
                y1 = box_pos[mid][1] + BOX_H // 2
                x2 = box_pos[tid][0]
                y2 = box_pos[tid][1] + BOX_H // 2
                if x2 < x1:
                    # цель левее (гранд-финал правее и ниже нижней сетки):
                    # уводим вправо, поднимаемся и заходим с правого края
                    x2r = x2 + BOX_W
                    xm = max(x1, x2r) + H_GAP // 4
                    pts = [(x1, y1), (xm, y1), (xm, y2), (x2r, y2)]
                elif kind == "lose":
                    # проигравший уходит в нижнюю сетку: сразу «ныряем» вниз
                    # в зазоре у правого края родного бокса — не перекрываем
                    # стрелку победителя, идущую по центру зазора выше
                    xm = x1 + H_GAP // 4
                    pts = [(x1, y1), (xm, y1), (xm, y2), (x2, y2)]
                else:
                    # обычный угловой переход вправо через середину зазора
                    xm = (x1 + x2) // 2
                    pts = [(x1, y1), (xm, y1), (xm, y2), (x2, y2)]
                color = LINE_COLORS.get(by_id[tid]["bracket"], "#2a4a6a")
                self.canvas.create_line(*[c for p in pts for c in p], fill=color, width=1)

        # ── Карточки и подписи поверх стрелок ──
        if l_rounds_list:
            self.canvas.create_text(
                X_START, Y_L_START - 46,
                text="⬇  НИЖНЯЯ СЕТКА (Losers Bracket)",
                fill="#cc6633", font=("Arial", 13, "bold"), anchor="w")

        for m, x, y, highlight in box_defs:
            self._draw_match_box(m, x, y, BOX_W, BOX_H, highlight=highlight)
        for tx, ty, text, fill, font, anchor in text_defs:
            self.canvas.create_text(tx, ty, text=text, fill=fill, font=font, anchor=anchor)

        total_w = X_START + max(len(w_rounds_list) + len(f_rounds), len(l_rounds_list) + 1) * (BOX_W + H_GAP) + BOX_W + 90
        total_h = Y_L_START
        if l_rounds_list:
            for ri, rmatches in enumerate(l_rounds_list):
                step_mult = 2 ** (ri // 2)
                step = (BOX_H + 22) * step_mult
                first_offset = (step - (BOX_H + 22)) // 2
                total_h = max(total_h, Y_L_START + first_offset + (len(rmatches) - 1) * step + BOX_H)
        else:
            total_h = max_y_w
        total_h += 60
        self.canvas.configure(scrollregion=(0, 0, total_w, total_h))

    def _on_canvas_wheel(self, event):
        """Вертикальный скролл сетки колесом мыши."""
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    def _on_canvas_hwheel(self, event):
        """Горизонтальный скролл сетки Shift+колесо (большие сетки шире окна)."""
        self.canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    @staticmethod
    def _round_rect(canvas, x1, y1, x2, y2, radius=14, **kwargs):
        r = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]
        return canvas.create_polygon(points, smooth=True, **kwargs)

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
            self._round_rect(c, x - 4, y - 4, x + w + 4, y + h + 4,
                        radius=16, fill="", outline="#00ff88", width=2)
        elif is_next:
            outline_color = "#ffaa33"
            outline_w = 3
            self._round_rect(c, x - 4, y - 4, x + w + 4, y + h + 4,
                        radius=16, fill="", outline="#ffaa33", width=2, dash=(5, 3))
        self._round_rect(c, x, y, x + w, y + h, radius=14,
                        fill=bg, outline=outline_color, width=outline_w)

        def pname(pid):
            if pid:
                p = self._participant_cache.get(pid)
                return p["name"] if p else "?"
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

        # Название раунда («1/4», «1/2», «Финал» и т.п.) здесь больше не
        # печатаем — оно и так видно один раз общим заголовком над колонкой
        # (см. _stage_label / _draw_bracket). Так карточка не загромождается
        # и имена участников никогда не наезжают на служебный текст.
        c.create_line(x + 1, y + h // 2, x + w - 1, y + h // 2, fill="#2a3f55", width=1)
        c.create_text(x + 10, y + h // 4, text=p1n[:28], fill=p1_color,
                    font=("Arial", 12, "bold"), anchor="w")
        c.create_text(x + 10, y + 3 * h // 4, text=p2n[:28], fill=p2_color,
                    font=("Arial", 12, "bold"), anchor="w")

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
            if m["status"] == "done":
                if m["winner_id"] == winner_id:
                    # Победитель не изменился — пересчёт не нужен.
                    return
                # Пересмотр результата: подтверждаем и пересчитываем сетку.
                winner_name = p1["name"] if winner_id == m["p1_id"] else p2["name"]
                if not messagebox.askyesno("Сменить победителя",
                        f"Матч завершён. Назначить победителем «{winner_name}»?\n\n"
                        "Сетка будет пересчитана до конца.", parent=self):
                    return
                ok = self.engine.change_winner(match_id, winner_id)
                if not ok:
                    messagebox.showwarning("Ошибка",
                            "Не удалось изменить победителя.", parent=self)
            else:
                self.engine.advance_winner(match_id, winner_id)
            self._invalidate_cache()
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
        matches = self._match_cache
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
                p = self._participant_cache.get(pid)
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
            p = self._participant_cache.get(s["pid"])
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
        cat_name = self._clean_category_name()
        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=f"protocol_{cat_name}_{self.hand}.pdf")
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

        # Формат зависит от системы розыгрыша турнира: single elimination —
        # до 1 поражения, double elimination — до 2 поражений.
        bracket_system = t["bracket_system"] if t and "bracket_system" in t.keys() else "double"
        format_label = "До 1 поражения" if bracket_system == "single" else "До 2 поражений"
        hand_label = "Двоеборье" if self.hand == "Обе" else self.hand
        story.append(Paragraph(
            f"Весовая категория: {cat_name}  |  Рука: {hand_label}  |  Формат: {format_label}",
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
                club_txt = p["club"] if p["club"] and p["club"] != "—" else ""
                data.append([
                    medals_txt.get(place, str(place)),
                    p["name"], club_txt,
                    str(p["weight"]) if p["weight"] else "—",
                    str(s["wins"]), str(s["losses"])
                ])
            col_widths = [2.5 * cm, 6 * cm, 4.5 * cm, 2 * cm, 2 * cm, 2.5 * cm]
            t_table = Table(data, colWidths=col_widths, repeatRows=1)
            t_row_sep = []
            for idx in range(len(standings)):
                t_row_sep.append(
                    ("LINEBELOW", (0, idx + 1), (-1, idx + 1), 1.4, colors.HexColor("#5b7b95")))
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
            ] + t_row_sep))
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
            m_row_sep = []
            for idx in range(len(m_data) - 1):
                m_row_sep.append(
                    ("LINEBELOW", (0, idx + 1), (-1, idx + 1), 1.0, colors.HexColor("#8aa2b8")))
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
            ] + m_row_sep))
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
        self.configure(fg_color=BG)
        self.after(50, self.safe_init)

    def safe_init(self):
        try:
            self._build_ui()
            self._refresh()
            self.deiconify()
            self.update_idletasks()
            _keep_topmost(self)
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Ошибка", str(e))
            self.destroy()

    def _build_ui(self):
        top = ctk.CTkFrame(self, fg_color=PANEL, height=55)
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
                    text="Очки: 1 место — 10 | 2 — 7 | 3 — 5 | 4 — 4 | 5 — 3 | 6 — 2 | 7 — 1 | 8 и ниже — 0   ·   при равных очках выше тот, у кого меньше вес; при равных очках и весе место делится, пока жюри не выберет победителя",
                    text_color="#aabbcc", font=ctk.CTkFont(size=11)
                    ).pack(padx=20, pady=8, anchor="w")

        header = ctk.CTkFrame(self, fg_color="#1a2535")
        header.pack(fill="x", padx=10, pady=(10, 0))
        headers = ["Место", "Спортсмен", "Клуб", "Вес", "Правая рука", "Левая рука", "Итого очков"]
        widths = [70, 210, 130, 70, 150, 150, 100]
        for i, (h, w) in enumerate(zip(headers, widths)):
            ctk.CTkLabel(header, text=h, font=ctk.CTkFont(size=12, weight="bold"),
                    width=w, anchor="w").grid(row=0, column=i, padx=6, pady=8, sticky="w")

        self.result_scroll = ScrollableFrame(self, fg_color=BG)
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
        widths = [70, 210, 130, 70, 150, 150, 100]
        for row in rows:
            place = row["place"]
            fg = PLACE_COLORS.get(place, "#1a2a3a")
            fr = ctk.CTkFrame(self.result_scroll, fg_color=fg, corner_radius=8)
            fr.pack(fill="x", padx=5, pady=3)
            medal = medals.get(place, f"#{place}")
            weight_txt = f"{row['weight']:.1f}" if row.get("weight") is not None else "—"
            values = [
                medal,
                row["name"],
                row["club"],
                weight_txt,
                self._fmt_hand(row["right_place"], row["right_points"]),
                self._fmt_hand(row["left_place"], row["left_points"]),
                str(row["total_points"]),
            ]
            for i, (val, w) in enumerate(zip(values, widths)):
                ctk.CTkLabel(fr, text=str(val), width=w, anchor="w",
                    font=ctk.CTkFont(size=13, weight="bold" if place <= 3 else "normal")
                    ).grid(row=0, column=i, padx=6, pady=8, sticky="w")

        # Панели «спора»: при одинаковых очках И весе жюри может вручную
        # выбрать победителя (или сбросить выбор).
        self._render_tie_bars(rows)

    def _render_tie_bars(self, rows):
        ties = []
        i = 0
        n = len(rows)
        while i < n:
            place = rows[i]["place"]
            j = i
            while j < n and rows[j]["place"] == place:
                j += 1
            group = rows[i:j]
            if len(group) > 1:
                ties.append(group)
            i = j
        for group in ties:
            place = group[0]["place"]
            fr = ctk.CTkFrame(self.result_scroll, fg_color="#2a2035", corner_radius=8)
            fr.pack(fill="x", padx=5, pady=(0, 3))
            ctk.CTkLabel(fr, text=f"Спор за {place}-е место (равные очки и вес):",
                    text_color="#cbb0e0", font=ctk.CTkFont(size=12, weight="bold")
                    ).pack(side="left", padx=10, pady=6)
            for row in group:
                ctk.CTkButton(fr, text=f"🏆 {row['name']}",
                        height=28, fg_color="#5a3a10", hover_color="#7a5a20",
                        command=lambda r=row: self._pick_tie_winner(place, group, r["pid"])
                        ).pack(side="left", padx=4, pady=6)
            ctk.CTkButton(fr, text="↩️ Сбросить",
                    height=28, fg_color="#333a44", hover_color="#4a5566",
                    command=lambda g=group: self._clear_tie_overrides(g)
                    ).pack(side="left", padx=10, pady=6)

    def _pick_tie_winner(self, place, group, winner_pid):
        others = [r["pid"] for r in group if r["pid"] != winner_pid]
        self.db.clear_dvoeborie_overrides(self.tournament_id, self.category["id"], others)
        self.db.set_dvoeborie_override(self.tournament_id, self.category["id"], winner_pid, place)
        self._push_overrides_sync()
        self._refresh()

    def _clear_tie_overrides(self, group):
        self.db.clear_dvoeborie_overrides(self.tournament_id, self.category["id"],
                                          [r["pid"] for r in group])
        self._push_overrides_sync()
        self._refresh()

    def _push_overrides_sync(self):
        """Отправляет на сайт полный снимок ручных мест двоеборья категории
        (замена). Если участник/категория ещё не синхронизированы — ждём
        следующего изменения."""
        try:
            from sync.sync_manager import sync_manager
        except Exception:
            return
        if not getattr(sync_manager, "enabled", False):
            return
        local = self.db.get_dvoeborie_overrides(
            self.tournament_id, self.category["id"])
        if not local:
            overrides = []
        else:
            remote_cat = sync_manager.state.map_get("category", self.category["id"])
            overrides = []
            for pid, manual_rank in local.items():
                remote_pid = sync_manager.state.map_get("participant", pid)
                if remote_cat is None or remote_pid is None:
                    return
                overrides.append({
                    "category_id": remote_cat,
                    "participant_id": remote_pid,
                    "manual_rank": manual_rank,
                })
        sync_manager.dispatch_async(
            lambda: sync_manager.on_dvoeborie_overrides_changed(
                self.tournament_id, overrides))

    def _clean_category_name(self):
        name = self.category["name"]
        name = re.sub(r"\s+Both\b", " Двоеборье", name)
        name = re.sub(r"\s+Left\b", "", name)
        name = re.sub(r"\s+Right\b", "", name)
        return name.strip()

    def _export_pdf(self):
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror("Ошибка", "Установите reportlab:\npip install reportlab")
            return
        rows = self._rows_cache or compute_dvoeborie_standings(self.db, self.engine, self.category)
        if not rows:
            messagebox.showwarning("Нет данных", "Нет результатов для экспорта.")
            return
        cat_name = self._clean_category_name()
        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=f"dvoeborie_{cat_name}.pdf")
        if not filepath:
            return

        doc = SimpleDocTemplate(filepath, pagesize=A4,
                    leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                    topMargin=2 * cm, bottomMargin=2 * cm)
        styles = getSampleStyleSheet()
        story = []

        title_style = ParagraphStyle("Title", parent=styles["Title"],
                    fontName="Arial-Bold", fontSize=18, spaceAfter=6, alignment=1)
        cat_hand = self.category["hand"] if "hand" in self.category.keys() else "Обе"
        hand_label = "Двоеборье" if cat_hand == "Обе" else (cat_hand or "Двоеборье")
        story.append(Paragraph(f"{cat_name} {hand_label}", title_style))

        t = self.db.get_tournament(self.tournament_id)
        if t:
            info_style = ParagraphStyle("Info", parent=styles["Normal"],
                    fontName="Arial", fontSize=11, spaceAfter=4, alignment=1)
            story.append(Paragraph(
                f"{t['name']}  |  {t['date']}  |  {t['location'] or ''}", info_style))

        story.append(Spacer(1, 0.3 * cm))

        data = [["Место", "Спортсмен", "Клуб", "Вес", "Правая рука", "Левая рука", "Итого очков"]]
        for row in rows:
            def fmt(place, points):
                return f"{place} место ({points})" if place else "— (0)"
            weight_txt = f"{row['weight']:.1f}" if row.get("weight") is not None else "—"
            club_txt = row["club"] if row.get("club") and row["club"] != "—" else ""
            data.append([
                str(row["place"]), row["name"], club_txt, weight_txt,
                fmt(row["right_place"], row["right_points"]),
                fmt(row["left_place"], row["left_points"]),
                str(row["total_points"]),
            ])
        col_widths = [1.6 * cm, 4.4 * cm, 2.9 * cm, 1.4 * cm, 3.1 * cm, 3.1 * cm, 2.2 * cm]
        table = Table(data, colWidths=col_widths, repeatRows=1)

        # Вертикальные линии-разделители между колонками (кроме последней).
        col_separators = []
        n_cols = len(data[0])
        for col in range(n_cols - 1):
            col_separators.append(
                ("LINEAFTER", (col, 0), (col, -1), 1.0, colors.HexColor("#b8c4d0")))

        # Горизонтальные полосы между строками данных.
        row_separators = []
        for idx in range(len(rows)):
            row_separators.append(
                ("LINEBELOW", (0, idx + 1), (-1, idx + 1), 1.4, colors.HexColor("#5b7b95")))

        medal_colors = {1: "#ffd700", 2: "#c0c0c0", 3: "#cd7f32"}
        background_cmds = []
        for idx, row in enumerate(rows, start=1):
            color = medal_colors.get(row["place"])
            if color:
                background_cmds.append(
                    ("BACKGROUND", (0, idx), (0, idx), colors.HexColor(color)))
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
        ] + col_separators + row_separators + background_cmds))
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
    def __init__(self, master, athlete, on_edit, on_delete, index=None,
                 on_show=None, on_hide=None, hidden=False, **kwargs):
        super().__init__(master, corner_radius=10, **kwargs)
        self.configure(fg_color=("#1e2a3a", "#1e2a3a"))
        a = athlete

        col = 0
        if index is not None:
            ctk.CTkLabel(self, text=f"#{index}", font=ctk.CTkFont(size=12, weight="bold"),
                        text_color="#556677", width=36).grid(row=0, column=0, rowspan=4, padx=(10, 0), pady=10)
            col = 1

        photo_label = ctk.CTkLabel(self, text="👤", font=("Arial", 30), width=120, height=140,
                    fg_color="#0d1420", corner_radius=14)
        local_photo = resolve_local_photo_path(a["photo_path"], only_cached=True) if PIL_AVAILABLE and a["photo_path"] else None
        if local_photo:
            try:
                img = load_photo_thumbnail(local_photo, 240, 280)
                photo = ctk.CTkImage(img, size=(120, 140))
                photo_label.configure(image=photo, text="", fg_color="transparent", corner_radius=0)
                photo_label._image = photo
            except Exception:
                pass
        photo_label.grid(row=0, column=col, rowspan=4, padx=(10, 8), pady=10)

        full_name = f"{a['last_name']} {a['first_name']}"
        name_label = ctk.CTkLabel(self, text=full_name, font=ctk.CTkFont(size=14, weight="bold"),
                    anchor="w")
        name_label.grid(row=0, column=col + 1, sticky="w", padx=5, pady=(10, 0))
        if hidden:
            ctk.CTkLabel(self, text="🙈 скрыт", font=ctk.CTkFont(size=10, weight="bold"),
                        text_color="#cc8844", anchor="w").grid(row=0, column=col + 2, sticky="w", padx=(0, 5), pady=(10, 0))

        gender_label = "Пол: Женский" if a["gender"] == "F" else "Пол: Мужской"
        turning_age = datetime.now().year - extract_birth_year(a["birth_date"])
        natural_cat = compute_age_category(a["birth_date"], a["gender"])
        iin_display = a["iin"] if a["iin"] else "—"
        info = f"🎂 {a['birth_date']} ({turning_age} лет)   {gender_label}   🏛 {a['club'] or 'без клуба'}   ИИН: {iin_display}"
        ctk.CTkLabel(self, text=info, font=ctk.CTkFont(size=11),
                    text_color="#8899aa", anchor="w").grid(row=1, column=col + 1, sticky="w", padx=5)

        cat_text = f"Категория: {natural_cat or '—'}"
        rank_phone_row = f"🥋 {a['rank']}" if a["rank"] else ""
        if a["phone"]:
            rank_phone_row += (f"   |   " if rank_phone_row else "") + f"📞 {a['phone']}"
        if rank_phone_row:
            cat_text += f"   |   {rank_phone_row}"
        ctk.CTkLabel(self, text=cat_text, font=ctk.CTkFont(size=11), text_color="#5588bb",
                    anchor="w").grid(row=2, column=col + 1, sticky="w", padx=5)

        coach_text = f"Тренер: {a['coach_name']}" if a["coach_name"] else "Тренер: отсутствует"
        ctk.CTkLabel(self, text=coach_text, font=ctk.CTkFont(size=11),
                    text_color="#44aa77", anchor="w").grid(row=3, column=col + 1, sticky="w", padx=5, pady=(0, 10))

        btn_col = col + 2
        if hidden:
            btn_col = col + 3
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=0, column=btn_col, rowspan=4, padx=10, pady=10, sticky="e")
        if hidden and on_show:
            ctk.CTkButton(btn_frame, text="👁 Показать", width=90, height=32,
                        fg_color="#2a4a2a", hover_color="#3a6a3a",
                        command=lambda: on_show(a["id"])).pack(pady=2)
        elif on_hide:
            ctk.CTkButton(btn_frame, text="🙈 Скрыть", width=90, height=32,
                        fg_color="#4a3a2a", hover_color="#6a5a3a",
                        command=lambda: on_hide(a["id"])).pack(pady=2)
        ctk.CTkButton(btn_frame, text="✏️", width=36, height=32,
                    command=lambda: on_edit(a["id"])).pack(pady=2)
        ctk.CTkButton(btn_frame, text="🗑", width=36, height=32,
                    fg_color=DANGER, hover_color=DANGER_HOVER,
                    command=lambda: on_delete(a["id"])).pack(pady=2)
        self.columnconfigure(col + 1, weight=1)


    # ════
    #  ОКНО «СПОРТСМЕНЫ» — общий реестр, не привязан к турниру
    # ════
class AthletesWindow(ctk.CTkFrame):
    def __init__(self, master, db):
        super().__init__(master, fg_color=BG, corner_radius=0)
        self.db = db
        self._build_ui()
        self._refresh_list()

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
        self.search_var.trace_add("write", lambda *_: self._schedule_refresh())
        ctk.CTkEntry(ctrl, textvariable=self.search_var, width=220,
                    placeholder_text="🔍 Поиск по имени/фамилии...").pack(side="left", padx=10)

        self.age_filter_var = ctk.StringVar(value="Все возрасты")
        age_options = ["Все возрасты"] + list(AGE_LEVEL_LABELS.values())
        OptionMenu(ctrl, variable=self.age_filter_var, values=age_options,
                    width=200, command=lambda *_: self._schedule_refresh()).pack(side="left", padx=5)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(0, 5))
        self.total_label = ctk.CTkLabel(header, text="", text_color="#556677")
        self.total_label.pack(side="left")

        # Пагинация: по 25 карточек на страницу — иначе с тысячами записей
        # каждый рендер пересоздавал бы десятки тысяч виджетов.
        self._page_size = 25
        self._page = 0
        self._total_pages = 1
        self._search_after = None

        self.list_frame = ScrollableFrame(self, fg_color=BG)
        self.list_frame.pack(fill="both", expand=True, padx=15, pady=(0, 5))

        paging = ctk.CTkFrame(self, fg_color="transparent")
        paging.pack(fill="x", padx=15, pady=(0, 10))
        self.page_label = ctk.CTkLabel(paging, text="", text_color="#8899aa")
        self.page_label.pack(side="left", padx=5)
        self.next_btn = ctk.CTkButton(paging, text="Вперёд ▶", width=90, height=30,
                    command=self._next_page)
        self.next_btn.pack(side="right", padx=5)
        self.prev_btn = ctk.CTkButton(paging, text="◀ Назад", width=90, height=30,
                    command=self._prev_page)
        self.prev_btn.pack(side="right", padx=5)

    def _schedule_refresh(self):
        """Debounce поиска/фильтра: перерисовываем не на каждый символ,
        а спустя 300мс после последнего изменения — иначе с тысячами
        записей каждый ввод символа пересоздавал бы все карточки."""
        if getattr(self, "_search_after", None):
            try:
                self.after_cancel(self._search_after)
            except Exception:
                pass
        self._search_after = self.after(300, self._debounced_refresh)

    def _debounced_refresh(self):
        self._search_after = None
        self._page = 0
        self._refresh_list()

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self._refresh_list()

    def _next_page(self):
        if self._page < self._total_pages - 1:
            self._page += 1
            self._refresh_list()

    def _update_paging(self, total):
        self._total_pages = max(1, math.ceil(total / self._page_size))
        if self._page >= self._total_pages:
            self._page = self._total_pages - 1
        self.page_label.configure(
            text=f"Стр. {self._page + 1} из {self._total_pages} · всего {total}")
        self.prev_btn.configure(state="normal" if self._page > 0 else "disabled")
        self.next_btn.configure(state="normal" if self._page < self._total_pages - 1 else "disabled")

    def _refresh_list(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        athletes = self.db.search_athletes(self.search_var.get().strip())

        selected_age = self.age_filter_var.get()
        if selected_age != "Все возрасты":
            label_to_level = {v: k for k, v in AGE_LEVEL_LABELS.items()}
            target_level = label_to_level[selected_age]
            athletes = [a for a in athletes if get_age_level(a["birth_date"]) == target_level]

        self.total_label.configure(text=f"👥 Всего спортсменов: {self.db.count_athletes()}")
        self._update_paging(len(athletes))
        start = self._page * self._page_size
        page_athletes = athletes[start:start + self._page_size]
        if not page_athletes:
            ctk.CTkLabel(self.list_frame, text="Нет спортсменов.",
                    text_color="#445566").pack(pady=20)
        else:
            for i, a in enumerate(page_athletes, start=start + 1):
                card = AthleteCard(self.list_frame, a,
                        on_edit=self._add_athlete_dialog,
                        on_delete=self._delete_athlete,
                        on_hide=self._hide_athlete, index=i)
                card.pack(fill="x", padx=5, pady=4)

        hidden = self.db.search_hidden_athletes(self.search_var.get().strip())
        if selected_age != "Все возрасты":
            hidden = [a for a in hidden if get_age_level(a["birth_date"]) == target_level]
        if hidden:
            ctk.CTkFrame(self.list_frame, height=2, fg_color="#334455").pack(fill="x", padx=5, pady=8)
            ctk.CTkLabel(self.list_frame,
                        text=f"🙈 Скрытые — убраны из реестра и с сайта ({len(hidden)})",
                        font=ctk.CTkFont(size=13, weight="bold"),
                        text_color="#cc8844", anchor="w").pack(fill="x", padx=5, pady=(4, 2))
            for i, a in enumerate(hidden, start=1):
                card = AthleteCard(self.list_frame, a,
                        on_edit=self._add_athlete_dialog,
                        on_delete=self._delete_athlete,
                        on_show=self._show_athlete, hidden=True, index=i)
                card.pack(fill="x", padx=5, pady=4)

    def _show_athlete(self, aid):
        """Вернуть спортсмена из «Скрытых» в обычный реестр (и на сайт)."""
        self.db.set_athlete_hidden(aid, False)
        self._refresh_list()

    def _hide_athlete(self, aid):
        if not messagebox.askyesno("Скрыть спортсмена",
                    "Скрыть спортсмена из реестра?\n\n"
                    "Он исчезнет из реестра и с сайта.\n"
                    "Можно вернуть кнопкой «👁 Показать» в секции «Скрытые».\n\n"
                    "Спортсмен покинет свой клуб (рейтинг клуба −10) и останется без тренера."):
            return
        self.db.set_athlete_hidden(aid, True)
        self._refresh_list()

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
        if entered != DELETE_PASSWORD:
            messagebox.showerror("Неверный пароль", "Удаление отменено.")
            return

        self.db.delete_athlete(aid)
        self._refresh_list()

    def _sync_now(self):
        """Ручная синхронизация из окна реестра: отправка офлайн-очереди на
        сайт + ПОЛНАЯ подтяжка карточек спортсменов/тренеров с сайта
        (в т.ч. тех, что ещё не внесены в десктоп). Сетевую часть делаем в
        фоне, чтобы не подвесить окно."""
        from sync.sync_manager import sync_manager

        def worker():
            pushed, remaining = 0, 0
            try:
                if sync_manager.state.pending_count() > 0:
                    pushed, remaining = sync_manager.flush_pending()
            except Exception as e:  # noqa: BLE001
                self.after(0, lambda: messagebox.showerror(
                    "Синхронизация", f"Ошибка отправки на сайт: {e}"))
                return
            try:
                from sync import pull_sync
                pulled = pull_sync.pull_sync_manager.sync_now()
            except Exception as e:  # noqa: BLE001
                self.after(0, lambda: messagebox.showerror(
                    "Синхронизация", f"Ошибка загрузки с сайта: {e}"))
                return
            self.after(0, lambda: self._sync_done(pushed, remaining, pulled))

        Thread(target=worker, daemon=True).start()

    def _sync_done(self, pushed, remaining, pulled):
        self._refresh_list()
        if remaining:
            messagebox.showwarning(
                "Синхронизация",
                f"Отправлено {pushed}, осталось {remaining} (похоже, связи всё ещё нет).\n"
                f"С сайта подтянуто записей: {pulled}."
            )
        else:
            messagebox.showinfo(
                "Синхронизация",
                f"Готово! Отправлено: {pushed}.\n"
                f"С сайта подтянуто новых/изменённых записей: {pulled}."
            )


    def _add_athlete_dialog(self, edit_id=None):
        dlg = tk.Toplevel(self)
        dlg.title("Редактировать спортсмена" if edit_id else "Добавить спортсмена")
        dlg.geometry("660x750")
        dlg.minsize(480, 740)
        dlg.configure(bg=PANEL)

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
            fields[key + "_entry"] = entry
            return var

        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=10, pady=15)

        lbl_entry(form, "Имя*:", "first_name", existing["first_name"] if existing else "", row=0)
        lbl_entry(form, "Фамилия*:", "last_name", existing["last_name"] if existing else "", row=1)
        lbl_entry(form, "ИИН* (12 цифр):", "iin", existing["iin"] if existing else "", row=2,
                  placeholder="12 цифр")

        iin_err_lbl = ctk.CTkLabel(form, text="", text_color=ERR,
                                   font=ctk.CTkFont(size=10), anchor="w")
        iin_err_lbl.grid(row=3, column=0, columnspan=2, padx=(128, 15), sticky="w")

        def check_iin_dup():
            value = fields["iin_entry"].get().strip()
            conflict = None
            if len(value) == 12 and value.isdigit():
                conflict = self.db.find_athlete_by_iin(value, exclude_id=edit_id)
            if conflict:
                iin_err_lbl.configure(
                    text="⚠ Спортсмен с таким ИИН уже существует", text_color=ERR)
            else:
                iin_err_lbl.configure(text="")

        def format_iin(event=None):
            raw = fields["iin_entry"].get()
            value = "".join(ch for ch in raw if ch.isdigit())[:12]
            if value != raw:
                fields["iin_entry"].delete(0, "end")
                fields["iin_entry"].insert(0, value)
                fields["iin_entry"].icursor(len(value))
            check_iin_dup()

        fields["iin_entry"].bind("<KeyRelease>", format_iin)
        check_iin_dup()

        # ─── Телефон с маской 8(XXX)XXX-XX-XX ───
        ctk.CTkLabel(form, text="Телефон:", anchor="e", width=110).grid(
            row=4, column=0, padx=(15, 8), pady=8, sticky="e")
        phone_var = ctk.StringVar(value="8(" if not existing else (existing["phone"] or "8("))
        phone_entry = ctk.CTkEntry(form, textvariable=phone_var, width=260,
                    placeholder_text="8(702)313-53-83")
        phone_entry.grid(row=4, column=1, padx=(0, 15), pady=8, sticky="w")
        fields["phone"] = phone_var

        def format_phone(event=None):
            raw = phone_entry.get()
            body = raw[2:] if raw.startswith("8(") else raw
            digits = "".join(ch for ch in body if ch.isdigit())
            if len(digits) == 11 and digits[0] in "87":
                digits = digits[1:]
            digits = digits[:10]
            if not digits:
                result = "8("
            elif len(digits) <= 3:
                result = f"8({digits}"
            elif len(digits) <= 6:
                result = f"8({digits[:3]}){digits[3:]}"
            elif len(digits) <= 8:
                result = f"8({digits[:3]}){digits[3:6]}-{digits[6:]}"
            else:
                result = f"8({digits[:3]}){digits[3:6]}-{digits[6:8]}-{digits[8:]}"
            phone_entry.delete(0, "end")
            phone_entry.insert(0, result)
            phone_entry.icursor(len(result))

        def block_extra(event=None):
            if not event.char or not event.char.isdigit():
                return None
            total = len("".join(ch for ch in phone_entry.get() if ch.isdigit()))
            if total >= 11:
                return "break"
            return None

        phone_entry.bind("<KeyRelease>", format_phone)
        phone_entry.bind("<Key>", block_extra)

        ctk.CTkLabel(form, text="Дата рожд.*:", anchor="e", width=110).grid(
            row=5, column=0, padx=(15, 8), pady=8, sticky="e")
        birth_date_var = ctk.StringVar(value=existing["birth_date"] if existing else "")
        birth_entry = ctk.CTkEntry(form, textvariable=birth_date_var, width=260,
                    placeholder_text="  .  .    ")
        birth_entry.grid(row=5, column=1, padx=(0, 15), pady=8, sticky="w")

        def format_birthdate(event=None):
            now_year = datetime.now().year
            value = "".join(ch for ch in birth_entry.get() if ch.isdigit())[:8]

            if len(value) >= 2:
                value = f"{min(31, max(1, int(value[:2]))):02d}" + value[2:]
            if len(value) >= 4:
                value = value[:2] + f"{min(12, max(1, int(value[2:4]))):02d}" + value[4:]
            if len(value) >= 8:
                value = value[:4] + f"{min(now_year, max(1920, int(value[4:8]))):04d}"

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
            row=6, column=0, padx=(15, 8), pady=8, sticky="e")
        gender_display = {"M": "Мужской", "F": "Женский"}
        gender_reverse = {"Мужской": "M", "Женский": "F"}
        gender_var = ctk.StringVar(
            value=gender_display.get(existing["gender"], "Мужской") if existing else "Мужской")
        OptionMenu(form, variable=gender_var,
                    values=["Мужской", "Женский"], width=260
                    ).grid(row=6, column=1, padx=(0, 15), pady=8, sticky="w")

        # ─── Клуб (выпадающий список из реестра «Клубы») ───
        _NO_CLUB = "— нет —"
        club_display_to_id = {_NO_CLUB: None}
        clubs = self.db.get_clubs()
        for cl in clubs:
            club_display_to_id[cl["name"]] = cl["id"]
        club_var = ctk.StringVar(value=_NO_CLUB)
        existing_club_name = _NO_CLUB
        if existing:
            if existing["club_id"]:
                cl_row = self.db.get_club(existing["club_id"])
                if cl_row:
                    existing_club_name = cl_row["name"]
                elif existing["club"]:
                    existing_club_name = existing["club"]
            elif existing["club"]:
                existing_club_name = existing["club"]
        if existing_club_name not in club_display_to_id:
            # Старый свободный текст клуба, которого нет в реестре — оставляем
            # как есть, чтобы при редактировании его не потерять.
            club_display_to_id[existing_club_name] = None
        club_var.set(existing_club_name)
        ctk.CTkLabel(form, text="Клуб:", anchor="e", width=110).grid(
            row=7, column=0, padx=(15, 8), pady=8, sticky="e")
        OptionMenu(form, variable=club_var,
                    values=list(club_display_to_id.keys()), width=260
                    ).grid(row=7, column=1, padx=(0, 15), pady=8, sticky="w")

        # ─── Звание (выпадающий список, обязательное) ───
        ctk.CTkLabel(form, text="Звание*:", anchor="e", width=110).grid(
            row=8, column=0, padx=(15, 8), pady=8, sticky="e")
        rank_var = ctk.StringVar(
            value=existing["rank"] if existing and existing["rank"] in RANKS else "Без звания")
        OptionMenu(form, variable=rank_var, values=RANKS, width=260
                    ).grid(row=8, column=1, padx=(0, 15), pady=8, sticky="w")

        # ─── Тренер (только при редактировании; при создании спортсмена
        # привязка к тренеру не делается — её выполняют отдельно, после
        # создания, через десктоп или админку) ───
        _NO_COACH = "— нет —"
        coach_display_to_id = {_NO_COACH: None}
        coach_var = ctk.StringVar(value=_NO_COACH)
        photo_row_num = 9

        if existing:
            ctk.CTkLabel(form, text="Тренер:", anchor="e", width=110).grid(
                row=9, column=0, padx=(15, 8), pady=8, sticky="e")
            coaches = self.db.get_coaches()
            for c in coaches:
                coach_display_to_id[c["full_name"]] = c["id"]
            existing_coach_name = _NO_COACH
            if existing["coach_id"]:
                row = self.db.get_coach(existing["coach_id"])
                if row:
                    existing_coach_name = row["full_name"]
            coach_var.set(existing_coach_name)
            OptionMenu(form, variable=coach_var,
                        values=[_NO_COACH] + [c["full_name"] for c in coaches], width=260
                        ).grid(row=9, column=1, padx=(0, 15), pady=8, sticky="w")
            photo_row_num = 10

        # ─── Фото (в отдельной строке, чтобы не наезжало на кнопку) ───
        ctk.CTkLabel(form, text="Фото:", anchor="e", width=110).grid(
            row=photo_row_num, column=0, padx=(15, 8), pady=8, sticky="e")
        photo_row = ctk.CTkFrame(form, fg_color="transparent")
        photo_row.grid(row=photo_row_num, column=1, padx=(0, 15), pady=8, sticky="w")

        photo_path_var.set(existing["photo_path"] or "" if existing else "")

        def choose_photo():
            p = filedialog.askopenfilename(
                filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")])
            if not p:
                return
            if not is_configured():
                messagebox.showwarning(
                    "Cloudinary не настроен",
                    "Загрузка фото недоступна: на этом компьютере не заданы "
                    "переменные окружения CLOUDINARY_CLOUD_NAME / "
                    "CLOUDINARY_UPLOAD_PRESET.\n\nСпортсмен будет сохранён без фото.")
                return

            photo_status_lbl.configure(text="Загружаем…", text_color="#c9a227")
            upload_btn.configure(state="disabled")

            def worker():
                try:
                    url = upload_photo(p, folder="athletes")
                except CloudinaryUploadError as e:
                    def on_error():
                        photo_status_lbl.configure(text=f"Ошибка: {e}", text_color=ERR)
                        upload_btn.configure(state="normal")
                    dlg.after(0, on_error)
                    return
                except Exception as e:
                    # Неожиданная ошибка не должна застрелять диалог на
                    # «Загружаем…» навсегда — показываем и возвращаем кнопку.
                    def on_error(e=e):
                        photo_status_lbl.configure(text=f"Ошибка: {e}", text_color=ERR)
                        upload_btn.configure(state="normal")
                    dlg.after(0, on_error)
                    return

                def on_success():
                    photo_path_var.set(url)
                    photo_status_lbl.configure(text="✓ Загружено", text_color=OK)
                    upload_btn.configure(state="normal")
                dlg.after(0, on_success)

            Thread(target=worker, daemon=True).start()

        upload_btn = ctk.CTkButton(photo_row, text="📷 Выбрать", width=110, height=28,
                    fg_color=ACCENT_DIM, hover_color=INFO_HOVER, command=choose_photo)
        upload_btn.pack(side="left")

        photo_status_lbl = ctk.CTkLabel(photo_row, text="не выбрано", text_color="#445566",
                    anchor="w", padx=8)
        photo_status_lbl.pack(side="left")

        if photo_path_var.get():
            photo_status_lbl.configure(text="✓ Фото есть", text_color=OK)

        preview_label = ctk.CTkLabel(form, text="", text_color="#5588bb",
                    font=ctk.CTkFont(size=11), anchor="w", justify="left")
        preview_label.grid(row=photo_row_num + 1, column=0, columnspan=2, padx=15, pady=(12, 0), sticky="w")

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

        def validate_iin(value):
            return bool(value and len(value) == 12 and value.isdigit())

        def save():
            first_name = fields["first_name"].get().strip()
            last_name = fields["last_name"].get().strip()
            birth_date = birth_date_var.get().strip()
            iin = fields["iin"].get().strip()
            phone = fields["phone"].get().strip()
            if not first_name or not last_name:
                messagebox.showwarning("Ошибка", "Введите имя и фамилию.")
                return
            if not validate_iin(iin):
                messagebox.showwarning("Ошибка", "ИИН должен содержать 12 цифр.")
                return
            if self.db.find_athlete_by_iin(iin, exclude_id=edit_id):
                messagebox.showwarning("Ошибка", "Спортсмен с таким ИИН уже существует.")
                return
            try:
                datetime.strptime(birth_date, "%d.%m.%Y")
            except ValueError:
                messagebox.showwarning("Ошибка", "Дата рождения в формате дд.мм.гггг (например, 25062002).")
                return
            dup = self.db.find_duplicate_athlete(first_name, last_name,
                                                 birth_date, exclude_id=edit_id)
            if dup:
                messagebox.showwarning(
                    "Возможный дубль",
                    f"Спортсмен с таким же именем и датой рождения уже существует:\n\n"
                    f"    {dup['last_name']} {dup['first_name']} ({dup['birth_date']})\n\n"
                    "Это только предупреждение — запись всё равно будет сохранена.")
            gender = gender_reverse[gender_var.get()]
            club_var_value = club_var.get()
            club_id = club_display_to_id.get(club_var_value)
            club = club_var_value if club_var_value != _NO_CLUB else ""
            rank = rank_var.get()
            coach_id = coach_display_to_id.get(coach_var.get())
            if edit_id:
                old = self.db.get_athlete(edit_id)
                old_club_id = old["club_id"] if old else None
                if old_club_id and old_club_id != club_id:
                    from club_rating import apply_athlete_removed
                    apply_athlete_removed(self.db.conn, edit_id, old_club_id)
                self.db.update_athlete(edit_id, first_name, last_name, birth_date,
                        gender, club, rank, photo_path_var.get(), coach_id,
                        iin=iin, phone=phone, club_id=club_id)
                if club_id and old_club_id != club_id:
                    from club_rating import mark_joined
                    mark_joined(self.db.conn, edit_id)
            else:
                new_id = self.db.add_athlete(first_name, last_name, birth_date,
                        gender, club, rank, photo_path_var.get(), coach_id,
                        iin=iin, phone=phone, club_id=club_id)
                if club_id:
                    from club_rating import mark_joined
                    mark_joined(self.db.conn, new_id)
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
    #  ОКНО «ТРЕНЕРЫ» — общий реестр, не привязан к турниру
    # ════
class CoachCard(ctk.CTkFrame):
    def __init__(self, master, coach, athletes_count, on_edit, on_delete, index=None,
                 on_show=None, on_hide=None, hidden=False, **kwargs):
        super().__init__(master, corner_radius=10, **kwargs)
        self.configure(fg_color=("#1e2a3a", "#1e2a3a"))
        c = coach

        col = 0
        if index is not None:
            ctk.CTkLabel(self, text=f"#{index}", font=ctk.CTkFont(size=12, weight="bold"),
                        text_color="#556677", width=36).grid(row=0, column=0, rowspan=4, padx=(10, 0), pady=10)
            col = 1

        photo_label = ctk.CTkLabel(self, text="🧑‍🏫", font=("Arial", 30), width=120, height=140,
                    fg_color="#0d1420", corner_radius=14)
        if PIL_AVAILABLE and c["photo_path"]:
            local_path = resolve_local_photo_path(c["photo_path"], only_cached=True)
            if local_path:
                try:
                    img = load_photo_thumbnail(local_path, 240, 280)
                    photo = ctk.CTkImage(light_image=img, dark_image=img, size=(120, 140))
                    photo_label.configure(image=photo, text="", fg_color="transparent", corner_radius=0)
                    photo_label._image = photo  # держим ссылку — иначе GC уберёт картинку
                except Exception:
                    pass
        photo_label.grid(row=0, column=col, rowspan=4, padx=(10, 8), pady=10)

        full_name = (c["full_name"] or "").strip()
        ctk.CTkLabel(self, text=full_name, font=ctk.CTkFont(size=14, weight="bold"),
                    anchor="w").grid(row=0, column=col + 1, sticky="w", padx=5, pady=(10, 0))
        if hidden:
            ctk.CTkLabel(self, text="🙈 скрыт", font=ctk.CTkFont(size=10, weight="bold"),
                        text_color="#cc8844", anchor="w").grid(row=0, column=col + 2, sticky="w", padx=(0, 5), pady=(10, 0))

        # ── дата рождения (возраст) ──
        age_label = birth_age_label(c["birth_date"]) or "дата рождения не указана"
        ctk.CTkLabel(self, text=f"🎂 {age_label}", font=ctk.CTkFont(size=11),
                    text_color="#8899aa", anchor="w").grid(row=1, column=col + 1, sticky="w", padx=5)

        # ── клуб · город/район · ИИН · телефон ──
        row2 = f"🏛 {c['club'] or 'без клуба'}"
        if c["city"]:
            row2 += f"   |   📍 {c['city']}"
        row2 += f"   |   ИИН: {c['iin'] or '—'}"
        if c["phone"]:
            row2 += f"   |   📞 {c['phone']}"
        ctk.CTkLabel(self, text=row2, font=ctk.CTkFont(size=11), text_color="#5588bb",
                    anchor="w").grid(row=2, column=col + 1, sticky="w", padx=5)

        # ── разряд · ученики ──
        row3 = f"🥋 {c['qualification'] or 'разряд не указан'}"
        row3 += f"   |   👥 учеников: {athletes_count}"
        ctk.CTkLabel(self, text=row3, font=ctk.CTkFont(size=11), text_color="#44aa77",
                    anchor="w").grid(row=3, column=col + 1, sticky="w", padx=5, pady=(0, 10))

        btn_col = col + 2
        if hidden:
            btn_col = col + 3
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=0, column=btn_col, rowspan=4, padx=10, pady=10, sticky="e")
        if hidden and on_show:
            ctk.CTkButton(btn_frame, text="👁 Показать", width=90, height=32,
                        fg_color="#2a4a2a", hover_color="#3a6a3a",
                        command=lambda: on_show(c["id"])).pack(pady=2)
        elif on_hide:
            ctk.CTkButton(btn_frame, text="🙈 Скрыть", width=90, height=32,
                        fg_color="#4a3a2a", hover_color="#6a5a3a",
                        command=lambda: on_hide(c["id"])).pack(pady=2)
        ctk.CTkButton(btn_frame, text="✏️", width=36, height=32,
                    command=lambda: on_edit(c["id"])).pack(pady=2)
        ctk.CTkButton(btn_frame, text="🗑", width=36, height=32,
                    fg_color=DANGER, hover_color=DANGER_HOVER,
                    command=lambda: on_delete(c["id"])).pack(pady=2)
        self.columnconfigure(col + 1, weight=1)


class CoachesWindow(ctk.CTkFrame):
    def __init__(self, master, db):
        super().__init__(master, fg_color=BG, corner_radius=0)
        self.db = db
        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", padx=15, pady=15)

        ctk.CTkButton(ctrl, text="➕ Добавить тренера", width=180, height=38,
                    fg_color="#1a4a2a", hover_color="#2a6a3a",
                    command=lambda: self._add_coach_dialog()).pack(side="left", padx=5)
        ctk.CTkButton(ctrl, text="🔄 Синхронизировать", width=170, height=38,
                    fg_color="#2a2a5a", hover_color="#3a3a7a",
                    command=self._sync_now).pack(side="left", padx=5)

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._schedule_refresh())
        ctk.CTkEntry(ctrl, textvariable=self.search_var, width=220,
                    placeholder_text="🔍 Поиск по ФИО...").pack(side="left", padx=10)

        self.count_label = ctk.CTkLabel(ctrl, text="", text_color="#556677")
        self.count_label.pack(side="right", padx=10)

        self._page_size = 25
        self._page = 0
        self._total_pages = 1
        self._search_after = None

        self.list_frame = ScrollableFrame(self, fg_color=BG)
        self.list_frame.pack(fill="both", expand=True, padx=15, pady=(0, 5))

        paging = ctk.CTkFrame(self, fg_color="transparent")
        paging.pack(fill="x", padx=15, pady=(0, 10))
        self.page_label = ctk.CTkLabel(paging, text="", text_color="#8899aa")
        self.page_label.pack(side="left", padx=5)
        self.next_btn = ctk.CTkButton(paging, text="Вперёд ▶", width=90, height=30,
                    command=self._next_page)
        self.next_btn.pack(side="right", padx=5)
        self.prev_btn = ctk.CTkButton(paging, text="◀ Назад", width=90, height=30,
                    command=self._prev_page)
        self.prev_btn.pack(side="right", padx=5)

    def _schedule_refresh(self):
        """Debounce поиска: перерисовываем спустя 300мс после последнего
        изменения — иначе с тысячами записей каждый символ пересоздавал бы
        все карточки."""
        if getattr(self, "_search_after", None):
            try:
                self.after_cancel(self._search_after)
            except Exception:
                pass
        self._search_after = self.after(300, self._debounced_refresh)

    def _debounced_refresh(self):
        self._search_after = None
        self._page = 0
        self._refresh_list()

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self._refresh_list()

    def _next_page(self):
        if self._page < self._total_pages - 1:
            self._page += 1
            self._refresh_list()

    def _update_paging(self, total):
        self._total_pages = max(1, math.ceil(total / self._page_size))
        if self._page >= self._total_pages:
            self._page = self._total_pages - 1
        self.page_label.configure(
            text=f"Стр. {self._page + 1} из {self._total_pages} · всего {total}")
        self.prev_btn.configure(state="normal" if self._page > 0 else "disabled")
        self.next_btn.configure(state="normal" if self._page < self._total_pages - 1 else "disabled")

    def _refresh_list(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        coaches = self.db.get_coaches(self.search_var.get().strip())
        self.count_label.configure(text=f"Всего: {len(coaches)}")
        self._update_paging(len(coaches))
        start = self._page * self._page_size
        page_coaches = coaches[start:start + self._page_size]
        if not page_coaches:
            ctk.CTkLabel(self.list_frame, text="Нет тренеров.",
                    text_color="#445566").pack(pady=20)
        else:
            for i, c in enumerate(page_coaches, start=start + 1):
                count = len(self.db.get_athletes_by_coach(c["id"]))
                card = CoachCard(self.list_frame, c, count,
                        on_edit=self._add_coach_dialog,
                        on_delete=self._delete_coach,
                        on_hide=self._hide_coach, index=i)
                card.pack(fill="x", padx=5, pady=4)

        hidden = self.db.search_hidden_coaches(self.search_var.get().strip())
        if hidden:
            ctk.CTkFrame(self.list_frame, height=2, fg_color="#334455").pack(fill="x", padx=5, pady=8)
            ctk.CTkLabel(self.list_frame,
                        text=f"🙈 Скрытые — убраны из реестра и с сайта ({len(hidden)})",
                        font=ctk.CTkFont(size=13, weight="bold"),
                        text_color="#cc8844", anchor="w").pack(fill="x", padx=5, pady=(4, 2))
            for i, c in enumerate(hidden, start=1):
                count = len(self.db.get_athletes_by_coach(c["id"]))
                card = CoachCard(self.list_frame, c, count,
                        on_edit=self._add_coach_dialog,
                        on_delete=self._delete_coach,
                        on_show=self._show_coach, hidden=True, index=i)
                card.pack(fill="x", padx=5, pady=4)

    def _sync_now(self):
        """Ручная синхронизация из окна реестра тренеров: отправка
        офлайн-очереди на сайт + ПОЛНАЯ подтяжка карточек с сайта (в т.ч.
        тех, что ещё не внесены в десктоп). Сетевую часть делаем в фоне,
        чтобы не подвесить окно."""
        from sync.sync_manager import sync_manager

        def worker():
            pushed, remaining = 0, 0
            try:
                if sync_manager.state.pending_count() > 0:
                    pushed, remaining = sync_manager.flush_pending()
            except Exception as e:  # noqa: BLE001
                self.after(0, lambda: messagebox.showerror(
                    "Синхронизация", f"Ошибка отправки на сайт: {e}"))
                return
            try:
                from sync import pull_sync
                pulled = pull_sync.pull_sync_manager.sync_now()
            except Exception as e:  # noqa: BLE001
                self.after(0, lambda: messagebox.showerror(
                    "Синхронизация", f"Ошибка загрузки с сайта: {e}"))
                return
            self.after(0, lambda: self._sync_done(pushed, remaining, pulled))

        Thread(target=worker, daemon=True).start()

    def _sync_done(self, pushed, remaining, pulled):
        self._refresh_list()
        if remaining:
            messagebox.showwarning(
                "Синхронизация",
                f"Отправлено {pushed}, осталось {remaining} (похоже, связи всё ещё нет).\n"
                f"С сайта подтянуто записей: {pulled}."
            )
        else:
            messagebox.showinfo(
                "Синхронизация",
                f"Готово! Отправлено: {pushed}.\n"
                f"С сайта подтянуто новых/изменённых записей: {pulled}."
            )

    def _show_coach(self, cid):
        """Вернуть тренера из «Скрытых» в обычный реестр (и на сайт)."""
        self.db.set_coach_hidden(cid, False)
        self._refresh_list()

    def _hide_coach(self, cid):
        if not messagebox.askyesno("Скрыть тренера",
                    "Скрыть тренера из реестра?\n\n"
                    "Он исчезнет из реестра и с сайта.\n"
                    "Можно вернуть кнопкой «👁 Показать» в секции «Скрытые».\n\n"
                    "Тренер покинет свой клуб, а его ученики останутся без тренера."):
            return
        self.db.set_coach_hidden(cid, True)
        self._refresh_list()

    def _delete_coach(self, cid):
        if not messagebox.askyesno("Удалить",
                    "Удалить тренера из реестра?\n"
                    "Его спортсмены не удаляются — просто останутся без тренера."):
            return

        entered = simpledialog.askstring(
            "Подтверждение", "Введите пароль для удаления:", show="*", parent=self
        )
        if entered is None:
            return
        if entered != DELETE_PASSWORD:
            messagebox.showerror("Неверный пароль", "Удаление отменено.")
            return

        self.db.delete_coach(cid)
        self._refresh_list()

    def _add_coach_dialog(self, edit_id=None):
        dlg = tk.Toplevel(self)
        dlg.title("Редактировать тренера" if edit_id else "Добавить тренера")
        if edit_id:
            dlg.geometry("1300x810")
            dlg.minsize(1300, 650)
            dlg.resizable(True, True)
        else:
            dlg.geometry("720x850")
            dlg.minsize(680, 790)
            dlg.resizable(False, False)
        dlg.configure(bg=BG)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.focus_force()

        existing = self.db.get_coach(edit_id) if edit_id else None
        fields = {}
        photo_path_var = ctk.StringVar(value=(existing["photo_path"] or "") if existing else "")

        # ─── helpers ────────────────────────────────────────────────
        def make_card(parent, **kw):
            card = ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=12,
                               border_width=1, border_color=BORDER)
            card.pack(**kw)
            return card

        def make_section_label(parent, text):
            ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=13, weight="bold"),
                        text_color="#8899aa").pack(anchor="w", padx=16, pady=(14, 6))

        def lbl_entry(parent, label, key, default="", row=0, placeholder="", width=240):
            ctk.CTkLabel(parent, text=label, anchor="e", width=90).grid(
                row=row, column=0, padx=(14, 6), pady=7, sticky="e")
            var = ctk.StringVar(value=default)
            ctk.CTkEntry(parent, textvariable=var, width=width, placeholder_text=placeholder,
                        fg_color=BG, border_color=BORDER).grid(
                row=row, column=1, padx=(0, 14), pady=7, sticky="ew")
            fields[key] = var
            return var

        # ═══ ВЕРХНЯЯ ПАНЕЛЬ: фото + имя + статус ══════════════════
        top_card = ctk.CTkFrame(dlg, fg_color=PANEL, corner_radius=12,
                               border_width=1, border_color=BORDER)
        top_card.pack(fill="x", padx=14, pady=(14, 0))

        top_inner = ctk.CTkFrame(top_card, fg_color="transparent")
        top_inner.pack(fill="x", padx=14, pady=12)

        photo_thumb_lbl = ctk.CTkLabel(top_inner, text="", width=64, height=64,
                                       corner_radius=32, fg_color=BG)
        photo_thumb_lbl.pack(side="left", padx=(0, 14))

        name_label = ctk.CTkLabel(top_inner, text="",
                    font=ctk.CTkFont(size=18, weight="bold"), text_color=TEXT)
        name_label.pack(side="left", anchor="s")

        if existing:
            name_label.configure(text=f"{existing['first_name']} {existing['last_name']}")

        def render_thumb(local_path):
            if not (PIL_AVAILABLE and local_path):
                photo_thumb_lbl.configure(image=None, text="👤", font=("Arial", 24))
                return
            try:
                img = load_photo_thumbnail(local_path, 64, 64)
                photo_img = ctk.CTkImage(light_image=img, dark_image=img, size=(64, 64))
                photo_thumb_lbl.configure(image=photo_img, text="")
                photo_thumb_lbl.image = photo_img
            except Exception:
                photo_thumb_lbl.configure(image=None, text="👤", font=("Arial", 24))

        if photo_path_var.get():
            # Сначала показываем только кэшированное фото (не блокируя UI
            # скачиванием), затем прогреваем Cloudinary в фоне и обновляем.
            render_thumb(resolve_local_photo_path(photo_path_var.get(), only_cached=True))
            def _thumb_warm_done():
                try:
                    if dlg.winfo_exists():
                        dlg.after(100, lambda: render_thumb(
                            resolve_local_photo_path(photo_path_var.get(), only_cached=True)))
                except Exception:
                    pass
            precache_photos([photo_path_var.get()], on_done=_thumb_warm_done)
        else:
            photo_thumb_lbl.configure(text="👤", font=("Arial", 24))

        # ═══ ОСНОВНАЯ ЧАСТЬ: две колонки ═══════════════════════════
        body = ctk.CTkFrame(dlg, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=(10, 0))
        body.grid_columnconfigure(0, weight=1, minsize=340)
        body.grid_rowconfigure(0, weight=1)
        if edit_id:
            body.grid_columnconfigure(1, weight=3)

        # ─── Левая колонка: анкета тренера ────────────────────────
        left_col = ScrollableFrame(body, fg_color="transparent")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 7))

        form_card = make_card(left_col, fill="x")
        make_section_label(form_card, "📋 Основная информация")

        form_grid = ctk.CTkFrame(form_card, fg_color="transparent")
        form_grid.pack(fill="x", padx=4, pady=(0, 12))
        form_grid.grid_columnconfigure(1, weight=1, minsize=240)

        lbl_entry(form_grid, "Имя*:", "first_name", existing["first_name"] if existing else "", row=0)
        lbl_entry(form_grid, "Фамилия*:", "last_name", existing["last_name"] if existing else "", row=1)

        ctk.CTkLabel(form_grid, text="Дата рожд.*:", anchor="e", width=90).grid(
            row=2, column=0, padx=(14, 6), pady=7, sticky="e")
        birth_date_var = ctk.StringVar(value=existing["birth_date"] if existing else "")
        birth_entry = ctk.CTkEntry(form_grid, textvariable=birth_date_var, width=240,
                    placeholder_text="  .  .    ", fg_color=BG, border_color=BORDER)
        birth_entry.grid(row=2, column=1, padx=(0, 14), pady=7, sticky="ew")

        def format_birthdate(event=None):
            now_year = datetime.now().year
            value = "".join(ch for ch in birth_entry.get() if ch.isdigit())[:8]

            if len(value) >= 2:
                value = f"{min(31, max(1, int(value[:2]))):02d}" + value[2:]
            if len(value) >= 4:
                value = value[:2] + f"{min(12, max(1, int(value[2:4]))):02d}" + value[4:]
            if len(value) >= 8:
                value = value[:4] + f"{min(now_year, max(1920, int(value[4:8]))):04d}"

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

        ctk.CTkLabel(form_grid, text="ИИН*:", anchor="e", width=90).grid(
            row=3, column=0, padx=(14, 6), pady=7, sticky="e")
        iin_var = ctk.StringVar(value=existing["iin"] if existing else "")
        iin_entry = ctk.CTkEntry(form_grid, textvariable=iin_var, width=240,
                    placeholder_text="12 цифр", fg_color=BG, border_color=BORDER)
        iin_entry.grid(row=3, column=1, padx=(0, 14), pady=7, sticky="ew")

        iin_err_lbl = ctk.CTkLabel(form_grid, text="", text_color=ERR,
                                   font=ctk.CTkFont(size=10), anchor="w")
        iin_err_lbl.grid(row=4, column=1, padx=(0, 14), pady=(0, 4), sticky="w")

        def check_iin_dup():
            value = iin_entry.get().strip()
            conflict = None
            if len(value) == 12 and value.isdigit():
                conflict = self.db.find_coach_by_iin(value, exclude_id=edit_id)
            if conflict:
                iin_err_lbl.configure(
                    text="⚠ Тренер с таким ИИН уже существует", text_color=ERR)
            else:
                iin_err_lbl.configure(text="")

        def format_iin(event=None):
            value = "".join(ch for ch in iin_entry.get() if ch.isdigit())[:12]
            if value != iin_entry.get():
                iin_entry.delete(0, "end")
                iin_entry.insert(0, value)
            check_iin_dup()

        iin_entry.bind("<KeyRelease>", format_iin)
        check_iin_dup()

        ctk.CTkLabel(form_grid, text="Звание:", anchor="e", width=90).grid(
            row=5, column=0, padx=(14, 6), pady=7, sticky="e")
        qualification_var = ctk.StringVar(
            value=existing["qualification"] if existing and existing["qualification"] in COACH_QUALIFICATIONS
            else COACH_QUALIFICATIONS[0])
        qualification_menu = OptionMenu(form_grid,
                    variable=qualification_var,
                    values=COACH_QUALIFICATIONS, width=240,
                    fg_color=BG, button_color="#2d333b",
                    dropdown_fg_color=DROPDOWN_BG)
        qualification_menu.grid(row=5, column=1, padx=(0, 14), pady=7, sticky="ew")

        # ─── Клуб (выпадающий список из реестра «Клубы») ───
        _NO_CLUB = "— нет —"
        club_display_to_id = {_NO_CLUB: None}
        clubs = self.db.get_clubs()
        for cl in clubs:
            club_display_to_id[cl["name"]] = cl["id"]
        existing_club_name = _NO_CLUB
        if existing:
            if existing["club_id"]:
                cl_row = self.db.get_club(existing["club_id"])
                if cl_row:
                    existing_club_name = cl_row["name"]
                elif existing["club"]:
                    existing_club_name = existing["club"]
            elif existing["club"]:
                existing_club_name = existing["club"]
        if existing_club_name not in club_display_to_id:
            # Старый свободный текст клуба, которого нет в реестре — оставляем
            # как есть, чтобы при редактировании его не потерять.
            club_display_to_id[existing_club_name] = None
        club_var = ctk.StringVar(value=existing_club_name)
        ctk.CTkLabel(form_grid, text="Клуб:", anchor="e", width=90).grid(
            row=6, column=0, padx=(14, 6), pady=7, sticky="e")
        OptionMenu(form_grid, variable=club_var,
                    values=list(club_display_to_id.keys()), width=240,
                    fg_color=BG, button_color="#2d333b",
                    dropdown_fg_color=DROPDOWN_BG
                    ).grid(row=6, column=1, padx=(0, 14), pady=7, sticky="ew")

        lbl_entry(form_grid, "Город/Район:", "city", (existing["city"] or "") if existing else "", row=7)

        # ─── Телефон (формат 8(XXX)XXX-XX-XX) ───
        ctk.CTkLabel(form_grid, text="Телефон:", anchor="e", width=90).grid(
            row=8, column=0, padx=(14, 6), pady=7, sticky="e")
        phone_var = ctk.StringVar(value="8(" if not existing else (existing["phone"] or "8("))
        phone_entry = ctk.CTkEntry(form_grid, textvariable=phone_var, width=240,
                    placeholder_text="8(702)313-53-83", fg_color=BG, border_color=BORDER)
        phone_entry.grid(row=8, column=1, padx=(0, 14), pady=7, sticky="ew")

        def format_phone(event=None):
            raw = phone_entry.get()
            # фиксированный префикс "8(" не считаем частью набираемых цифр
            body = raw[2:] if raw.startswith("8(") else raw
            digits = "".join(ch for ch in body if ch.isdigit())
            if len(digits) == 11 and digits[0] in "87":
                digits = digits[1:]
            digits = digits[:10]
            if not digits:
                result = "8("
            elif len(digits) <= 3:
                result = f"8({digits}"
            elif len(digits) <= 6:
                result = f"8({digits[:3]}){digits[3:]}"
            elif len(digits) <= 8:
                result = f"8({digits[:3]}){digits[3:6]}-{digits[6:]}"
            else:
                result = f"8({digits[:3]}){digits[3:6]}-{digits[6:8]}-{digits[8:]}"
            phone_entry.delete(0, "end")
            phone_entry.insert(0, result)
            phone_entry.icursor(len(result))

        phone_entry.bind("<KeyRelease>", format_phone)

        def block_extra(event=None):
            if not event.char or not event.char.isdigit():
                return None
            # в поле всегда лежит префиксный "8" + до 10 набираемых цифр,
            # поэтому больше 11 цифр в тексте набрать нельзя
            total = len("".join(ch for ch in phone_entry.get() if ch.isdigit()))
            if total >= 11:
                return "break"
            return None

        phone_entry.bind("<Key>", block_extra)

        # ─── Фото ───
        photo_card = make_card(left_col, fill="x", pady=(8, 0))
        make_section_label(photo_card, "🖼 Фотография")

        photo_row = ctk.CTkFrame(photo_card, fg_color="transparent")
        photo_row.pack(fill="x", padx=14, pady=(0, 14))

        def choose_photo():
            p = filedialog.askopenfilename(
                filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")])
            if not p:
                return
            if not is_configured():
                messagebox.showwarning(
                    "Cloudinary не настроен",
                    "Загрузка фото недоступна: на этом компьютере не заданы "

                    "переменные окружения CLOUDINARY_CLOUD_NAME / "
                    "CLOUDINARY_UPLOAD_PRESET.\n\nТренер будет сохранён без фото.")
                return

            render_thumb(p)
            photo_status_lbl.configure(text="Загружаем…", text_color="#c9a227")
            upload_btn.configure(state="disabled")

            def worker():
                try:
                    url = upload_photo(p, folder="coaches")
                except CloudinaryUploadError as e:
                    def on_error():
                        photo_status_lbl.configure(text=f"Ошибка: {e}", text_color=ERR)
                        upload_btn.configure(state="normal")
                    dlg.after(0, on_error)
                    return
                except Exception as e:
                    # Неожиданная ошибка не должна застрелять диалог на
                    # «Загружаем…» навсегда — показываем и возвращаем кнопку.
                    def on_error(e=e):
                        photo_status_lbl.configure(text=f"Ошибка: {e}", text_color=ERR)
                        upload_btn.configure(state="normal")
                    dlg.after(0, on_error)
                    return

                def on_success():
                    photo_path_var.set(url)
                    photo_status_lbl.configure(text="✓ Загружено", text_color=OK)
                    upload_btn.configure(state="normal")
                dlg.after(0, on_success)

            Thread(target=worker, daemon=True).start()

        upload_btn = ctk.CTkButton(photo_row, text="📷 Выбрать фото", width=120, height=32,
                    fg_color=ACCENT_DIM, hover_color=INFO_HOVER,
                    command=choose_photo)
        upload_btn.pack(side="left")

        photo_status_lbl = ctk.CTkLabel(photo_row, text="не выбрано", text_color=TEXT_FAINT,
                    anchor="w", padx=10)
        photo_status_lbl.pack(side="left")

        if photo_path_var.get():
            photo_status_lbl.configure(text="✓ Загружено", text_color=OK)

        # ─── Правая колонка: ученики ────────────────────────────
        if existing:
            right_col = ctk.CTkFrame(body, fg_color="transparent")
            right_col.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
            right_col.grid_rowconfigure(1, weight=1)
            right_col.grid_columnconfigure(0, weight=1)

            # ── Поиск спортсмена (попап, как в диалоге участника) ──
            search_card = make_card(right_col, fill="x")
            make_section_label(search_card, "🔗 Привязать спортсмена")

            search_row = ctk.CTkFrame(search_card, fg_color="transparent")
            search_row.pack(fill="x", padx=14, pady=(0, 14))

            assigned_ids = {a["id"] for a in self.db.get_athletes_by_coach(edit_id)}

            def open_athlete_picker():
                picker = tk.Toplevel(dlg)
                picker.title("Выбрать спортсмена")
                sw, sh = picker.winfo_screenwidth(), picker.winfo_screenheight()
                picker.geometry(f"480x540+{(sw-480)//2}+{(sh-540)//2}")
                picker.configure(bg=BG)
                picker.transient(dlg)
                picker.grab_set()
                picker.focus_force()

                search_var = ctk.StringVar()
                ctk.CTkEntry(picker, textvariable=search_var, width=440,
                            placeholder_text="🔍 Поиск по имени или фамилии...",
                            fg_color=BG, border_color=BORDER
                            ).pack(padx=14, pady=(14, 6))

                results_frame = ScrollableFrame(picker, fg_color=BG)
                results_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))

                def refresh_picker():
                    for w in results_frame.winfo_children():
                        w.destroy()
                    q = search_var.get().strip()
                    if len(q) < 1:
                        ctk.CTkLabel(results_frame, text="Введите имя для поиска",
                                    text_color=TEXT_FAINT).pack(pady=30)
                        return
                    try:
                        found = self.db.search_athletes(q)
                    except Exception:
                        found = []
                    if not found:
                        ctk.CTkLabel(results_frame, text="Спортсмены не найдены",
                                    text_color=TEXT_FAINT).pack(pady=30)
                        return
                    for a in found:
                        if a["id"] in assigned_ids:
                            continue
                        age = datetime.now().year - extract_birth_year(a["birth_date"])
                        club = a["club"] or "—"
                        label = f"{a['last_name']} {a['first_name']}  ·  {age} лет  ·  {club}"

                        def pick(a=a):
                            try:
                                self.db.update_athlete(
                                    a["id"], a["first_name"], a["last_name"],
                                    a["birth_date"], a["gender"], a["club"],
                                    a["rank"], a["photo_path"], edit_id,
                                    club_id=a["club_id"],
                                )
                                assigned_ids.add(a["id"])
                                refresh_athletes_list()
                                picker.destroy()
                            except Exception as e:
                                messagebox.showerror("Ошибка", f"Не удалось привязать:\n{e}")

                        ctk.CTkButton(results_frame, text=label, anchor="w",
                                    fg_color=CARD, hover_color="#1c2333",
                                    border_width=1, border_color=BORDER,
                                    command=pick, height=36
                                    ).pack(fill="x", padx=4, pady=3)

                search_var.trace_add("write", lambda *_: refresh_picker())
                refresh_picker()

            ctk.CTkButton(search_row, text="🔍 Выбрать спортсмена",
                        fg_color=ACCENT_DIM, hover_color=INFO_HOVER,
                        height=36, command=open_athlete_picker
                        ).pack(fill="x")

            # ── Список учеников ──
            students_card = make_card(right_col, fill="both", expand=True, pady=(8, 0))

            students_header = ctk.CTkFrame(students_card, fg_color="transparent")
            students_header.pack(fill="x", padx=16, pady=(14, 6))
            ctk.CTkLabel(students_header, text="👥 Ученики",
                        font=ctk.CTkFont(size=13, weight="bold"),
                        text_color="#8899aa").pack(side="left")

            count_lbl = ctk.CTkLabel(students_header, text="0",
                        fg_color=BORDER, corner_radius=8,
                        padx=6, text_color=TEXT_FAINT,
                        font=ctk.CTkFont(size=11))
            count_lbl.pack(side="left", padx=(8, 0))

            athletes_card = ctk.CTkFrame(students_card, fg_color=BG,
                        corner_radius=10, border_width=1, border_color=BORDER)
            athletes_card.pack(fill="both", expand=True, padx=14, pady=(0, 14))
            athletes_card.grid_rowconfigure(0, weight=1)
            athletes_card.grid_columnconfigure(0, weight=1)

            athletes_frame = ScrollableFrame(athletes_card, fg_color="transparent")
            athletes_frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

            def refresh_athletes_list():
                for w in athletes_frame.winfo_children():
                    w.destroy()
                nonlocal assigned_ids
                assigned = self.db.get_athletes_by_coach(edit_id)
                assigned_ids = {a["id"] for a in assigned}
                count_lbl.configure(text=str(len(assigned)))
                if not assigned:
                    empty = ctk.CTkFrame(athletes_frame, fg_color="transparent")
                    empty.pack(fill="both", expand=True, pady=30)
                    ctk.CTkLabel(empty, text="🤷", font=("Arial", 28)).pack()
                    ctk.CTkLabel(empty, text="Нет привязанных спортсменов",
                                text_color=TEXT_FAINT).pack(pady=(4, 0))
                for i, a in enumerate(assigned, 1):
                    row = ctk.CTkFrame(athletes_frame, fg_color=CARD,
                                       corner_radius=8, border_width=1, border_color=BORDER)
                    row.pack(fill="x", padx=6, pady=3)
                    age = datetime.now().year - extract_birth_year(a["birth_date"])
                    club = a["club"] or ""
                    num_lbl = ctk.CTkLabel(row, text=f"{i}.", width=28, anchor="e",
                                           text_color=TEXT_FAINT, font=ctk.CTkFont(size=12))
                    num_lbl.pack(side="left", padx=(8, 2), pady=8)
                    info = f"{a['last_name']} {a['first_name']}  ·  {age} лет"
                    if club:
                        info += f"  ·  {club}"
                    ctk.CTkLabel(row, text=info, anchor="w",
                                font=ctk.CTkFont(size=12)).pack(side="left", padx=4, pady=8)

                    def unassign(aid=a["id"]):
                        try:
                            row_data = self.db.get_athlete(aid)
                            self.db.update_athlete(
                                aid, row_data["first_name"], row_data["last_name"],
                                row_data["birth_date"], row_data["gender"],
                                row_data["club"], row_data["rank"],
                                row_data["photo_path"], None,
                                club_id=row_data["club_id"],
                            )
                            assigned_ids.discard(aid)
                            refresh_athletes_list()
                        except Exception as e:
                            messagebox.showerror("Ошибка", f"Не удалось отвязать:\n{e}")

                    ctk.CTkButton(row, text="✕", width=32, height=26,
                                fg_color="#3a1010", hover_color="#5a2020",
                                corner_radius=6,
                                command=unassign).pack(side="right", padx=(4, 8), pady=6)

            refresh_athletes_list()

        # ═══ КНОПКИ ═══════════════════════════════════════════════
        btn_bar = ctk.CTkFrame(dlg, fg_color=BG)
        btn_bar.pack(fill="x", padx=14, pady=(10, 14))

        def save():
            nonlocal edit_id
            first_name = fields["first_name"].get().strip()
            last_name = fields["last_name"].get().strip()
            if not first_name or not last_name:
                messagebox.showwarning("Ошибка", "Введите имя и фамилию тренера.")
                return
            birth_date = birth_date_var.get().strip()
            try:
                datetime.strptime(birth_date, "%d.%m.%Y")
            except ValueError:
                messagebox.showwarning("Ошибка",
                    "Дата рождения в формате дд.мм.гггг (например, 25.06.2002).")
                return
            iin = iin_var.get().strip()
            if len(iin) != 12 or not iin.isdigit():
                messagebox.showwarning("Ошибка", "ИИН должен состоять ровно из 12 цифр.")
                return
            if self.db.find_coach_by_iin(iin, exclude_id=edit_id):
                messagebox.showwarning("Ошибка", "Тренер с таким ИИН уже существует.")
                return
            full_name = f"{last_name} {first_name}".strip()
            dup = self.db.find_duplicate_coach(full_name, birth_date,
                                               exclude_id=edit_id)
            if dup:
                messagebox.showwarning(
                    "Возможный дубль",
                    f"Тренер с таким же именем и датой рождения уже существует:\n\n"
                    f"    {dup['full_name']} ({dup['birth_date']})\n\n"
                    "Это только предупреждение — запись всё равно будет сохранена.")
            qualification = qualification_var.get()
            club_var_value = club_var.get()
            club_id = club_display_to_id.get(club_var_value)
            club = club_var_value if club_var_value != _NO_CLUB else ""
            city = fields["city"].get().strip()
            phone = phone_var.get().strip()
            photo_path = photo_path_var.get()
            if edit_id:
                self.db.update_coach(edit_id, full_name, club, photo_path, "",
                        first_name, last_name, birth_date, iin, qualification, city,
                        phone, club_id=club_id)
            else:
                edit_id = self.db.add_coach(full_name, club, photo_path, "",
                        first_name, last_name, birth_date, iin, qualification, city,
                        phone, club_id=club_id)
            self._refresh_list()
            dlg.destroy()

        ctk.CTkButton(btn_bar, text="💾 Сохранить", fg_color=SUCCESS,
                    hover_color=SUCCESS_HOVER, height=38, width=120,
                    corner_radius=8, command=save).pack(side="right", padx=(6, 0))
        ctk.CTkButton(btn_bar, text="Отмена", fg_color=DROPDOWN_BG,
                    hover_color="#30363d", height=38, width=100,
                    corner_radius=8,
                    command=lambda: (self._refresh_list(), dlg.destroy())
                    ).pack(side="right", padx=(0, 6))


# ════
#  ОКНО «КЛУБЫ» — реестр клубов с привязкой спортсменов и тренеров
# ════
class ClubCard(ctk.CTkFrame):
    def __init__(self, master, club, athletes_count, coaches_count, on_edit, on_delete, index=None, db=None, **kwargs):
        super().__init__(master, corner_radius=10, **kwargs)
        self.configure(fg_color=("#1e2a3a", "#1e2a3a"))
        c = club

        col = 0
        if index is not None:
            ctk.CTkLabel(self, text=f"#{index}", font=ctk.CTkFont(size=12, weight="bold"),
                        text_color="#556677", width=36).grid(row=0, column=0, rowspan=2, padx=(10, 0), pady=10)
            col = 1

        ctk.CTkLabel(self, text="🏛", font=("Arial", 26), width=56).grid(
            row=0, column=col, rowspan=2, padx=(10, 8), pady=10)

        ctk.CTkLabel(self, text=c["name"], font=ctk.CTkFont(size=14, weight="bold"),
                    anchor="w").grid(row=0, column=col + 1, sticky="w", padx=5, pady=(10, 0))

        info_parts = []
        if c["city"]:
            info_parts.append(f"📍 {c['city']}")
        if c["address"]:
            info_parts.append(f"🏢 {c['address']}")
        if c["phone"]:
            info_parts.append(f"📞 {c['phone']}")
        if c["founded_year"]:
            info_parts.append(f"📅 с {c['founded_year']}")
        info_parts.append(f"👤 спортсменов: {athletes_count}")
        info_parts.append(f"🧑‍🏫 тренеров: {coaches_count}")
        ctk.CTkLabel(self, text="   ".join(info_parts), font=ctk.CTkFont(size=11),
                    text_color="#8899aa", anchor="w").grid(row=1, column=col + 1, sticky="w", padx=5, pady=(0, 10))

        try:
            from club_rating import get_club_rating
            rating = get_club_rating(db.conn, c["id"]) if db is not None else 0
            rating_text = f"⭐ {rating} баллов" if db is not None else ""
        except Exception:
            rating_text = ""
        if rating_text:
            ctk.CTkLabel(self, text=rating_text, font=ctk.CTkFont(size=12, weight="bold"),
                        text_color="#c9a227", anchor="w").grid(row=0, column=col + 2, sticky="e", padx=5, pady=5)
            btn_col = col + 3
        else:
            btn_col = col + 2

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=0, column=btn_col, rowspan=2, padx=10, pady=10, sticky="e")
        ctk.CTkButton(btn_frame, text="✏️", width=36, height=32,
                    command=lambda: on_edit(c["id"])).pack(pady=2)
        ctk.CTkButton(btn_frame, text="🗑", width=36, height=32,
                    fg_color=DANGER, hover_color=DANGER_HOVER,
                    command=lambda: on_delete(c["id"])).pack(pady=2)
        self.columnconfigure(col + 1, weight=1)


class ClubsWindow(ctk.CTkFrame):
    def __init__(self, master, db):
        super().__init__(master, fg_color=BG, corner_radius=0)
        self.db = db
        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", padx=15, pady=15)

        ctk.CTkButton(ctrl, text="➕ Добавить клуб", width=160, height=38,
                    fg_color="#1a4a2a", hover_color="#2a6a3a",
                    command=lambda: self._add_club_dialog()).pack(side="left", padx=5)
        ctk.CTkButton(ctrl, text="🔄 Синхронизировать", width=170, height=38,
                    fg_color="#2a2a5a", hover_color="#3a3a7a",
                    command=self._sync_now).pack(side="left", padx=5)

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._schedule_refresh())
        ctk.CTkEntry(ctrl, textvariable=self.search_var, width=220,
                    placeholder_text="🔍 Поиск по названию...").pack(side="left", padx=10)

        self.count_label = ctk.CTkLabel(ctrl, text="", text_color="#556677")
        self.count_label.pack(side="right", padx=10)

        self._page_size = 25
        self._page = 0
        self._total_pages = 1
        self._search_after = None

        self.list_frame = ScrollableFrame(self, fg_color=BG)
        self.list_frame.pack(fill="both", expand=True, padx=15, pady=(0, 5))

        paging = ctk.CTkFrame(self, fg_color="transparent")
        paging.pack(fill="x", padx=15, pady=(0, 10))
        self.page_label = ctk.CTkLabel(paging, text="", text_color="#8899aa")
        self.page_label.pack(side="left", padx=5)
        self.next_btn = ctk.CTkButton(paging, text="Вперёд ▶", width=90, height=30,
                    command=self._next_page)
        self.next_btn.pack(side="right", padx=5)
        self.prev_btn = ctk.CTkButton(paging, text="◀ Назад", width=90, height=30,
                    command=self._prev_page)
        self.prev_btn.pack(side="right", padx=5)

    def _schedule_refresh(self):
        """Debounce поиска: перерисовываем спустя 300мс после последнего
        изменения — иначе с тысячами записей каждый символ пересоздавал бы
        все карточки."""
        if getattr(self, "_search_after", None):
            try:
                self.after_cancel(self._search_after)
            except Exception:
                pass
        self._search_after = self.after(300, self._debounced_refresh)

    def _debounced_refresh(self):
        self._search_after = None
        self._page = 0
        self._refresh_list()

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self._refresh_list()

    def _next_page(self):
        if self._page < self._total_pages - 1:
            self._page += 1
            self._refresh_list()

    def _update_paging(self, total):
        self._total_pages = max(1, math.ceil(total / self._page_size))
        if self._page >= self._total_pages:
            self._page = self._total_pages - 1
        self.page_label.configure(
            text=f"Стр. {self._page + 1} из {self._total_pages} · всего {total}")
        self.prev_btn.configure(state="normal" if self._page > 0 else "disabled")
        self.next_btn.configure(state="normal" if self._page < self._total_pages - 1 else "disabled")

    def _refresh_list(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        clubs = self.db.get_clubs(self.search_var.get().strip())
        self.count_label.configure(text=f"Всего: {len(clubs)}")
        self._update_paging(len(clubs))
        start = self._page * self._page_size
        page_clubs = clubs[start:start + self._page_size]
        if not page_clubs:
            ctk.CTkLabel(self.list_frame, text="Нет клубов.",
                    text_color="#445566").pack(pady=20)
            return
        for i, cl in enumerate(page_clubs, start=start + 1):
            athletes_count = len(self.db.get_athletes_by_club(cl["id"]))
            coaches_count = len(self.db.get_coaches_by_club(cl["id"]))
            card = ClubCard(self.list_frame, cl, athletes_count, coaches_count,
                    on_edit=self._add_club_dialog,
                    on_delete=self._delete_club, index=i, db=self.db)
            card.pack(fill="x", padx=5, pady=4)

    def _sync_now(self):
        """Ручная синхронизация из окна реестра клубов: отправка офлайн-очереди
        на сайт + ПОЛНАЯ подтяжка клубов/спортсменов/тренеров с сайта (в т.ч.
        тех, что ещё не внесены в десктоп). Сетевую часть делаем в фоне,
        чтобы не подвесить окно."""
        from sync.sync_manager import sync_manager

        def worker():
            pushed, remaining = 0, 0
            try:
                if sync_manager.state.pending_count() > 0:
                    pushed, remaining = sync_manager.flush_pending()
            except Exception as e:  # noqa: BLE001
                self.after(0, lambda: messagebox.showerror(
                    "Синхронизация", f"Ошибка отправки на сайт: {e}"))
                return
            try:
                from sync import pull_sync
                pulled = pull_sync.pull_sync_manager.sync_now()
            except Exception as e:  # noqa: BLE001
                self.after(0, lambda: messagebox.showerror(
                    "Синхронизация", f"Ошибка загрузки с сайта: {e}"))
                return
            self.after(0, lambda: self._sync_done(pushed, remaining, pulled))

        Thread(target=worker, daemon=True).start()

    def _sync_done(self, pushed, remaining, pulled):
        self._refresh_list()
        if remaining:
            messagebox.showwarning(
                "Синхронизация",
                f"Отправлено {pushed}, осталось {remaining} (похоже, связи всё ещё нет).\n"
                f"С сайта подтянуто записей: {pulled}."
            )
        else:
            messagebox.showinfo(
                "Синхронизация",
                f"Готово! Отправлено: {pushed}.\n"
                f"С сайта подтянуто новых/изменённых записей: {pulled}."
            )

    def _delete_club(self, cid):
        cl = self.db.get_club(cid)
        if not messagebox.askyesno("Удалить",
                    f"Удалить клуб «{cl['name']}»?\n"
                    "Спортсмены и тренеры не удаляются — просто останутся без клуба."):
            return
        self.db.delete_club(cid)
        self._refresh_list()

    def _add_club_dialog(self, edit_id=None):
        dlg = tk.Toplevel(self)
        dlg.title("Редактировать клуб" if edit_id else "Добавить клуб")
        if edit_id:
            dlg.geometry("1160x740")
            dlg.minsize(920, 560)
            dlg.resizable(True, True)
        else:
            dlg.geometry("760x600")
            dlg.minsize(700, 560)
            dlg.resizable(False, False)
        dlg.configure(bg=BG)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.focus_force()

        existing = self.db.get_club(edit_id) if edit_id else None
        logo_path_var = ctk.StringVar(value=(existing["logo_path"] or "") if existing else "")

        def make_card(parent, **kw):
            card = ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=12,
                               border_width=1, border_color=BORDER)
            card.pack(**kw)
            return card

        def make_section_label(parent, text):
            ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=13, weight="bold"),
                        text_color="#8899aa").pack(anchor="w", padx=16, pady=(14, 6))

        def lbl_entry(parent, label, key, default="", row=0, placeholder="", width=240):
            ctk.CTkLabel(parent, text=label, anchor="e", width=110).grid(
                row=row, column=0, padx=(14, 6), pady=7, sticky="e")
            var = ctk.StringVar(value=default)
            ctk.CTkEntry(parent, textvariable=var, width=width, placeholder_text=placeholder,
                        fg_color=BG, border_color=BORDER).grid(
                row=row, column=1, padx=(0, 14), pady=7, sticky="ew")
            fields[key] = var
            return var

        fields = {}

        # ─── Акценты: спортсмены — синий, тренеры — латунь ─────
        ATH_ACCENT = "#1f6feb"
        COACH_ACCENT = "#c9a227"

        # ─── Шапка диалога ──────────────────────────────────────
        header = ctk.CTkFrame(dlg, fg_color=PANEL, corner_radius=0, height=62)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="🏛", font=("Arial", 24)).pack(side="left", padx=(16, 10))
        title_col = ctk.CTkFrame(header, fg_color="transparent")
        title_col.pack(side="left")
        ctk.CTkLabel(title_col, text="Клуб",
                    font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(title_col,
                    text="Новый клуб в реестре" if not existing else "Карточка клуба в реестре",
                    font=ctk.CTkFont(size=11), text_color=TEXT_FAINT).pack(anchor="w")
        ctk.CTkFrame(header, fg_color=ATH_ACCENT, height=2).pack(fill="x", side="bottom")

        # ─── Левая колонка: анкета клуба ───────────────────────
        left_col = ctk.CTkFrame(dlg, fg_color="transparent")
        left_col.pack(side="left", fill="both", expand=True, padx=(14, 7), pady=14)

        form_card = make_card(left_col, fill="x")
        make_section_label(form_card, "📋 Информация о клубе")

        form_grid = ctk.CTkFrame(form_card, fg_color="transparent")
        form_grid.pack(fill="x", padx=4, pady=(0, 12))
        form_grid.grid_columnconfigure(1, weight=1, minsize=240)
        lbl_entry(form_grid, "Название*:", "name", existing["name"] if existing else "", row=0)
        lbl_entry(form_grid, "Город/Область:", "city", (existing["city"] or "") if existing else "", row=1)
        lbl_entry(form_grid, "Адрес зала:", "address", (existing["address"] or "") if existing else "", row=2)
        lbl_entry(form_grid, "Год основания:", "founded_year",
                  str(existing["founded_year"]) if existing and existing["founded_year"] else "", row=3)

        # ─── Телефон (формат 8(XXX)XXX-XX-XX) ───
        ctk.CTkLabel(form_grid, text="Телефон:", anchor="e", width=110).grid(
            row=4, column=0, padx=(14, 6), pady=7, sticky="e")
        phone_var = ctk.StringVar(value="8(" if not existing else (existing["phone"] or "8("))
        phone_entry = ctk.CTkEntry(form_grid, textvariable=phone_var, width=240,
                    placeholder_text="8(702)313-53-83", fg_color=BG, border_color=BORDER)
        phone_entry.grid(row=4, column=1, padx=(0, 14), pady=7, sticky="ew")

        def format_phone(event=None):
            raw = phone_entry.get()
            body = raw[2:] if raw.startswith("8(") else raw
            digits = "".join(ch for ch in body if ch.isdigit())
            if len(digits) == 11 and digits[0] in "87":
                digits = digits[1:]
            digits = digits[:10]
            if not digits:
                result = "8("
            elif len(digits) <= 3:
                result = f"8({digits}"
            elif len(digits) <= 6:
                result = f"8({digits[:3]}){digits[3:]}"
            elif len(digits) <= 8:
                result = f"8({digits[:3]}){digits[3:6]}-{digits[6:]}"
            else:
                result = f"8({digits[:3]}){digits[3:6]}-{digits[6:8]}-{digits[8:]}"
            phone_entry.delete(0, "end")
            phone_entry.insert(0, result)
            phone_entry.icursor(len(result))

        phone_entry.bind("<KeyRelease>", format_phone)

        def block_extra(event=None):
            if not event.char or not event.char.isdigit():
                return None
            total = len("".join(ch for ch in phone_entry.get() if ch.isdigit()))
            if total >= 11:
                return "break"
            return None

        phone_entry.bind("<Key>", block_extra)

        # ─── Логотип ───
        logo_card = make_card(left_col, fill="x", pady=(8, 0))
        make_section_label(logo_card, "🖼 Логотип")

        logo_row = ctk.CTkFrame(logo_card, fg_color="transparent")
        logo_row.pack(fill="x", padx=14, pady=(0, 14))

        logo_status_lbl = ctk.CTkLabel(logo_row, text="не выбрано", text_color=TEXT_FAINT,
                    anchor="w", padx=10)
        logo_status_lbl.pack(side="left")

        def choose_logo():
            p = filedialog.askopenfilename(
                filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")])
            if not p:
                return
            if not is_configured():
                messagebox.showwarning(
                    "Cloudinary не настроен",
                    "Загрузка лого недоступна: не заданы переменные окружения "
                    "CLOUDINARY_CLOUD_NAME / CLOUDINARY_UPLOAD_PRESET.\n\n"
                    "Клуб будет сохранён без лого.")
                return
            logo_status_lbl.configure(text="Загружаем…", text_color="#c9a227")

            def worker():
                try:
                    url = upload_photo(p, folder="clubs")
                except CloudinaryUploadError as e:
                    dlg.after(0, lambda e=e: logo_status_lbl.configure(
                        text=f"Ошибка: {e}", text_color=ERR))
                    return
                except Exception as e:
                    # Неожиданная ошибка не должна застрелять диалог на
                    # «Загружаем…» навсегда — показываем и возвращаем кнопку.
                    dlg.after(0, lambda e=e: logo_status_lbl.configure(
                        text=f"Ошибка: {e}", text_color=ERR))
                    return
                dlg.after(0, lambda: (logo_path_var.set(url),
                                      logo_status_lbl.configure(text="✓ Загружено", text_color=OK)))

            Thread(target=worker, daemon=True).start()

        ctk.CTkButton(logo_row, text="📷 Выбрать лого", width=120, height=32,
                    fg_color=ACCENT_DIM, hover_color=INFO_HOVER,
                    command=choose_logo).pack(side="left")

        if logo_path_var.get():
            logo_status_lbl.configure(text="✓ Загружено", text_color=OK)

        # ─── Правая колонка: спортсмены и тренеры клуба ────────
        right_col = ctk.CTkFrame(dlg, fg_color="transparent")
        if edit_id:
            right_col.pack(side="right", fill="both", expand=True, padx=(7, 14), pady=14)

        members_scroll = ScrollableFrame(right_col, fg_color=BG)
        members_scroll.pack(fill="both", expand=True)

        def member_row(parent, text, accent, on_remove):
            row = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=8)
            row.pack(fill="x", padx=2, pady=3)
            ctk.CTkFrame(row, fg_color=accent, width=3, height=30,
                        corner_radius=0).pack(side="left", padx=(0, 8), fill="y")
            ctk.CTkLabel(row, text=text, anchor="w",
                        font=ctk.CTkFont(size=12)).pack(side="left", padx=(6, 6),
                                                        pady=7, fill="x", expand=True)
            ctk.CTkButton(row, text="✕", width=30, height=26, fg_color=DANGER,
                        hover_color=DANGER_HOVER, command=on_remove).pack(side="right", padx=6)
            return row

        def make_members_card(kind):
            """Отдельная секция с заголовком, счётчиком и кнопкой «Добавить»."""
            is_ath = kind == "athletes"
            accent = ATH_ACCENT if is_ath else COACH_ACCENT
            icon = "👤" if is_ath else "🧑‍🏫"
            title = "Спортсмены" if is_ath else "Тренеры"
            empty_text = ("Пока нет спортсменов в клубе" if is_ath
                          else "Пока нет тренеров в клубе")

            card = ctk.CTkFrame(members_scroll, fg_color=PANEL, corner_radius=12,
                                border_width=1, border_color=BORDER)
            card.pack(fill="x", pady=(0, 10))

            head = ctk.CTkFrame(card, fg_color="transparent")
            head.pack(fill="x", padx=14, pady=(12, 4))
            ctk.CTkLabel(head, text=f"{icon} {title}",
                        font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
            count_badge = ctk.CTkLabel(head, text="0", text_color="#0d1117",
                        corner_radius=6, font=ctk.CTkFont(size=11, weight="bold"),
                        fg_color=accent, width=26, height=20)
            count_badge.pack(side="left", padx=(8, 0))

            list_frame = ctk.CTkFrame(card, fg_color="transparent")
            list_frame.pack(fill="x", padx=10, pady=(2, 8))

            def add_member():
                if is_ath:
                    self._add_athlete_to_club(edit_id, render_all)
                else:
                    self._add_coach_to_club(edit_id, render_all)

            ctk.CTkButton(card, text="➕ Добавить", width=120, height=30,
                        fg_color=accent, hover_color=accent,
                        command=add_member).pack(anchor="w", padx=14, pady=(0, 12))

            return card, list_frame, count_badge, empty_text

        def render_all():
            for w in members_scroll.winfo_children():
                w.destroy()

            if not existing:
                hint = ctk.CTkFrame(members_scroll, fg_color="transparent",
                                    border_width=1, border_color=BORDER,
                                    corner_radius=12)
                hint.pack(fill="x", padx=2, pady=20)
                ctk.CTkLabel(hint, text="🏛 Новый клуб",
                            font=ctk.CTkFont(size=14, weight="bold"),
                            text_color="#8899aa").pack(pady=(26, 4))
                ctk.CTkLabel(hint,
                            text="Сохраните клуб, чтобы привязывать к нему\nспортсменов и тренеров.",
                            text_color=TEXT_FAINT).pack(pady=(0, 26))
                return

            athletes = self.db.get_athletes_by_club(edit_id)
            coaches = self.db.get_coaches_by_club(edit_id)

            # ─── Рейтинг клуба (баллы + история) ─────────────────
            rating_card = ctk.CTkFrame(members_scroll, fg_color=PANEL, corner_radius=12,
                                       border_width=1, border_color=BORDER)
            rating_card.pack(fill="x", pady=(0, 10))
            rating_head = ctk.CTkFrame(rating_card, fg_color="transparent")
            rating_head.pack(fill="x", padx=14, pady=(12, 4))
            ctk.CTkLabel(rating_head, text="⭐ Рейтинг клуба",
                        font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")

            from club_rating import check_inactive_athletes, get_club_rating, get_club_rating_history
            try:
                check_inactive_athletes(self.db.conn)
            except Exception:
                pass
            rating = get_club_rating(self.db.conn, edit_id)
            ctk.CTkLabel(rating_head, text=f"{rating} баллов",
                        font=ctk.CTkFont(size=14, weight="bold"),
                        text_color="#c9a227").pack(side="right", padx=(8, 14))

            hist_frame = ctk.CTkFrame(rating_card, fg_color="transparent")
            hist_frame.pack(fill="x", padx=10, pady=(2, 8))
            history = get_club_rating_history(self.db.conn, edit_id)
            if not history:
                ctk.CTkLabel(hist_frame, text="Пока нет записей",
                            text_color=TEXT_FAINT, font=ctk.CTkFont(size=11)).pack(pady=8)
            for h in history[:20]:
                sign = f"+{h['points']}" if h["points"] > 0 else str(h["points"])
                color = "#2fbf71" if h["points"] > 0 else ERR
                who = h["athlete_name"] or "—"
                evt = h["tournament_name"] or "—"
                when = str(h["created_at"])[:10] if h["created_at"] else ""
                row = ctk.CTkFrame(hist_frame, fg_color=CARD, corner_radius=8)
                row.pack(fill="x", padx=2, pady=2)
                ctk.CTkLabel(row, text=f"{sign}  {h['description']}  ·  {who}  ·  {evt}",
                            anchor="w", font=ctk.CTkFont(size=11), text_color=color
                            ).pack(side="left", padx=(8, 4), pady=5, fill="x", expand=True)
                ctk.CTkLabel(row, text=when, anchor="e",
                            font=ctk.CTkFont(size=10), text_color=TEXT_FAINT
                            ).pack(side="right", padx=8)

            ath_card, ath_list, ath_badge, ath_empty = make_members_card("athletes")
            ath_badge.configure(text=str(len(athletes)))
            if not athletes:
                ctk.CTkLabel(ath_list, text=ath_empty, text_color=TEXT_FAINT,
                            font=ctk.CTkFont(size=11)).pack(pady=10)
            for a in athletes:
                name = f"{a['last_name']} {a['first_name']}".strip()
                member_row(ath_list, name, ATH_ACCENT,
                           lambda aid=a["id"]: self._remove_athlete_from_club(aid, render_all))

            coach_card, coach_list, coach_badge, coach_empty = make_members_card("coaches")
            coach_badge.configure(text=str(len(coaches)))
            if not coaches:
                ctk.CTkLabel(coach_list, text=coach_empty, text_color=TEXT_FAINT,
                            font=ctk.CTkFont(size=11)).pack(pady=10)
            for c in coaches:
                member_row(coach_list, c["full_name"], COACH_ACCENT,
                           lambda cid=c["id"]: self._remove_coach_from_club(cid, render_all))

        render_all()

        # ─── Кнопки сохранения ─────────────────────────────────
        btn_bar = ctk.CTkFrame(dlg, fg_color=BG)
        btn_bar.pack(fill="x", padx=14, pady=(10, 14), side="bottom")

        def save():
            name = fields["name"].get().strip()
            if not name:
                messagebox.showwarning("Ошибка", "Введите название клуба.")
                return
            city = fields["city"].get().strip()
            address = fields["address"].get().strip()
            founded_raw = fields["founded_year"].get().strip()
            founded_year = None
            if founded_raw:
                try:
                    founded_year = int(founded_raw)
                except ValueError:
                    messagebox.showwarning("Ошибка", "Год основания — целое число (например, 2015).")
                    return
            logo_path = logo_path_var.get()
            phone = phone_var.get().strip() or ""
            nonlocal edit_id
            if edit_id:
                self.db.update_club(edit_id, name, city, address, founded_year, logo_path, phone)
            else:
                edit_id = self.db.add_club(name, city, address, founded_year, logo_path, phone)
            self._refresh_list()
            dlg.destroy()

        ctk.CTkButton(btn_bar, text="💾 Сохранить", fg_color=SUCCESS,
                    hover_color=SUCCESS_HOVER, height=38, width=120,
                    corner_radius=8, command=save).pack(side="right", padx=(6, 0))
        ctk.CTkButton(btn_bar, text="Отмена", fg_color=DROPDOWN_BG,
                    hover_color="#30363d", height=38, width=100,
                    corner_radius=8,
                    command=lambda: (self._refresh_list(), dlg.destroy())
                    ).pack(side="right", padx=(0, 6))

    # ── привязка/отвязка членов клуба ──────────────────────────
    def _add_athlete_to_club(self, club_id, on_done=None):
        club = self.db.get_club(club_id)
        picker = tk.Toplevel(self)
        picker.title("Выбрать спортсмена для клуба")
        sw, sh = picker.winfo_screenwidth(), picker.winfo_screenheight()
        picker.geometry(f"480x540+{(sw-480)//2}+{(sh-540)//2}")
        picker.configure(bg=BG)
        picker.transient(self.winfo_toplevel())
        picker.grab_set()

        search_var = ctk.StringVar()
        ctk.CTkEntry(picker, textvariable=search_var, width=440,
                    placeholder_text="🔍 Поиск по имени или фамилии...",
                    fg_color=BG, border_color=BORDER
                    ).pack(padx=14, pady=(14, 6))

        results_frame = ScrollableFrame(picker, fg_color=BG)
        results_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        def refresh():
            for w in results_frame.winfo_children():
                w.destroy()
            q = search_var.get().strip()
            if len(q) < 1:
                ctk.CTkLabel(results_frame, text="Введите имя для поиска",
                            text_color=TEXT_FAINT).pack(pady=30)
                return
            try:
                found = self.db.search_athletes(q)
            except Exception:
                found = []
            if not found:
                ctk.CTkLabel(results_frame, text="Спортсмены не найдены",
                            text_color=TEXT_FAINT).pack(pady=30)
                return
            for a in found:
                if a["club_id"] == club_id:
                    continue
                label = f"{a['last_name']} {a['first_name']}"
                try:
                    age = datetime.now().year - extract_birth_year(a["birth_date"])
                    label += f"  ·  {age} лет"
                except Exception:
                    pass
                if a["club"]:
                    label += f"  ·  {a['club']}"

                def pick(a=a):
                    try:
                        self.db.update_athlete(
                            a["id"], a["first_name"], a["last_name"],
                            a["birth_date"], a["gender"], club["name"],
                            a["rank"], a["photo_path"], a["coach_id"],
                            iin=a["iin"], phone=a["phone"], club_id=club_id)
                        from club_rating import mark_joined
                        mark_joined(self.db.conn, a["id"])
                        if on_done:
                            on_done()
                        picker.destroy()
                    except Exception as e:
                        messagebox.showerror("Ошибка", f"Не удалось привязать:\n{e}")

                ctk.CTkButton(results_frame, text=label, anchor="w",
                            fg_color=CARD, hover_color="#1c2333",
                            command=pick).pack(fill="x", padx=5, pady=2)

        search_var.trace_add("write", lambda *_: refresh())
        refresh()

    def _add_coach_to_club(self, club_id, on_done=None):
        club = self.db.get_club(club_id)
        picker = tk.Toplevel(self)
        picker.title("Выбрать тренера для клуба")
        sw, sh = picker.winfo_screenwidth(), picker.winfo_screenheight()
        picker.geometry(f"480x540+{(sw-480)//2}+{(sh-540)//2}")
        picker.configure(bg=BG)
        picker.transient(self.winfo_toplevel())
        picker.grab_set()

        search_var = ctk.StringVar()
        ctk.CTkEntry(picker, textvariable=search_var, width=440,
                    placeholder_text="🔍 Поиск по ФИО...",
                    fg_color=BG, border_color=BORDER
                    ).pack(padx=14, pady=(14, 6))

        results_frame = ScrollableFrame(picker, fg_color=BG)
        results_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        def refresh():
            for w in results_frame.winfo_children():
                w.destroy()
            q = search_var.get().strip()
            if len(q) < 1:
                ctk.CTkLabel(results_frame, text="Введите имя для поиска",
                            text_color=TEXT_FAINT).pack(pady=30)
                return
            try:
                found = self.db.get_coaches(q)
            except Exception:
                found = []
            if not found:
                ctk.CTkLabel(results_frame, text="Тренеры не найдены",
                            text_color=TEXT_FAINT).pack(pady=30)
                return
            for c in found:
                if c["club_id"] == club_id:
                    continue
                label = c["full_name"]
                if c["club"]:
                    label += f"  ·  {c['club']}"

                def pick(c=c):
                    try:
                        self.db.update_coach(
                            c["id"], c["full_name"], club["name"], c["photo_path"], c["bio"],
                            c["first_name"], c["last_name"], c["birth_date"], c["iin"],
                            c["qualification"], c["city"], club_id=club_id)
                        if on_done:
                            on_done()
                        picker.destroy()
                    except Exception as e:
                        messagebox.showerror("Ошибка", f"Не удалось привязать:\n{e}")

                ctk.CTkButton(results_frame, text=label, anchor="w",
                            fg_color=CARD, hover_color="#1c2333",
                            command=pick).pack(fill="x", padx=5, pady=2)

        search_var.trace_add("write", lambda *_: refresh())
        refresh()

    def _remove_athlete_from_club(self, aid, on_done=None):
        a = self.db.get_athlete(aid)
        if a:
            from club_rating import apply_athlete_removed
            apply_athlete_removed(self.db.conn, aid, a["club_id"])
            self.db.update_athlete(aid, a["first_name"], a["last_name"], a["birth_date"],
                                   a["gender"], "", a["rank"], a["photo_path"], a["coach_id"],
                                   iin=a["iin"], phone=a["phone"], club_id=None)
        if on_done:
            on_done()

    def _remove_coach_from_club(self, cid, on_done=None):
        c = self.db.get_coach(cid)
        if c:
            self.db.update_coach(cid, c["full_name"], "", c["photo_path"], c["bio"],
                                 c["first_name"], c["last_name"], c["birth_date"], c["iin"],
                                 c["qualification"], c["city"], club_id=None)
        if on_done:
            on_done()


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
        self._pending_select = None

        self.title("🦾 ArmWrestling Tournament Manager")
        self.minsize(900, 600)
        self.configure(fg_color=BG)

        # Стартовый размер — на случай если zoomed вообще не применится
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")

        def _apply_fullscreen():
            try:
                self.state("zoomed")
            except Exception:
                try:
                    self.attributes("-zoomed", True)
                except Exception:
                    self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")

        # Применяем "zoomed" ПОСЛЕ того как окно замаплено — иначе виден
        # промежуточный кадр с маленьким размером ("прыжок" разрешения).
        self.after(10, _apply_fullscreen)

        self._build_ui()
        self._refresh_status_badge()
        self._refresh_tournament_list()
        self._start_auto_sync()
        self._start_pull_sync()

        # Экспорт/импорт и авто-бэкапы: конфигурация и тикеры.
        try:
            backup_manager.configure(conn=self.db.conn, state=sync_manager.state,
                                     backup_dir=str(BACKUP_DIR))
            self._last_blocked = False
            self.after(2000, self._status_tick)
            self.after(2500, self._startup_recovery_check)
        except Exception as e:
            print(f"[transfer] init: {e}")

        # Проверка неактивных спортсменов (клубный рейтинг) после старта UI.
        self.after(1500, self._check_club_inactivity)
        # Проверка подключения к серверу синхронизации (неблокирующая).
        self.after(3000, self._backend_health_check)

    def _backend_health_check(self):
        """Разовая неблокирующая проверка доступности сервера синхронизации
        при старте. НЕ висит: HTTP-запрос выполняется в фоновом потоке с
        таймаутом (см. config.REQUEST_TIMEOUT_SECONDS), UI не блокируется.
        Показывает понятный тост, а не «тихо молчит»."""
        def _probe():
            try:
                from sync import config as sync_config
                from sync.api_client import SyncApiClient
                api = SyncApiClient()
                api.timeout = min(api.timeout or 10, 10)
                api.ping()
                ok, msg = True, ""
            except Exception as e:
                ok, msg = False, str(e)
            self.after(0, lambda: self._show_backend_health_result(ok, msg))
        Thread(target=_probe, daemon=True).start()

    def _show_backend_health_result(self, ok, msg):
        try:
            from sync import config as sync_config
            host = sync_config.API_BASE_URL
            if ok:
                self._show_sync_toast(
                    f"🟢 Сервер синхронизации доступен")
            else:
                low = msg.lower()
                if ("timed out" in low or "conn" in low or "resolve" in low):
                    reason = "нет интернета"
                else:
                    reason = "токен или адрес сервера"
                self._show_sync_toast(
                    f"⚠️ Сервер синхронизации недоступен ({reason}). "
                    f"Проверьте подключение к интернету.\n{host}")
        except Exception:
            pass

    def _check_club_inactivity(self):
        try:
            from club_rating import check_inactive_athletes
            n = check_inactive_athletes(self.db.conn)
            if n:
                print(f"club rating: {n} спортсменов отмечены неактивными")
        except Exception as e:
            print("club rating inactivity check error:", e)

    def _build_ui(self):
        self.sidebar = ctk.CTkFrame(self, width=240, corner_radius=0, fg_color=PANEL)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        ctk.CTkLabel(self.sidebar,
                    text="🦾 ArmWrestling\nTournament",
                    font=ctk.CTkFont(size=16, weight="bold"),
                    text_color=ACCENT).pack(pady=(22, 4), padx=15)
        ctk.CTkLabel(self.sidebar, text="Manager + Scanner",
                    font=ctk.CTkFont(size=11),
                    text_color=TEXT_FAINT).pack(pady=(0, 26))

        self.nav_buttons = {}
        nav_items = [
            ("tournaments", "🏆  Турниры"),
            ("athletes", "👤  Спортсмены"),
            ("coaches", "🧑‍🏫  Тренеры"),
            ("clubs", "🏛  Клубы"),
        ]
        for key, text in nav_items:
            btn = ctk.CTkButton(self.sidebar, text=text, height=42,
                        corner_radius=8, anchor="w",
                        fg_color="transparent", hover_color=PANEL_LIGHT,
                        text_color=TEXT_DIM, font=ctk.CTkFont(size=13),
                        command=lambda k=key: self._show_page(k))
            btn.pack(fill="x", padx=12, pady=4)
            self.nav_buttons[key] = btn

        self.main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.main.pack(side="right", fill="both", expand=True)

        self.pages = {}
        self._build_tournaments_page()
        self._build_athletes_page()
        self._build_coaches_page()
        self._build_clubs_page()
        self._show_page("tournaments")

    def _show_page(self, name):
        """Переключает страницы в главной области: прячет остальные и
        показывает выбранную, подсвечивая активную кнопку сайдбара."""
        self.current_page = name
        for key, page in self.pages.items():
            if key == name:
                page.pack(fill="both", expand=True)
            else:
                page.pack_forget()
        for key, btn in self.nav_buttons.items():
            active = (key == name)
            btn.configure(
                fg_color=ACCENT_DIM if active else "transparent",
                hover_color=ACCENT_HOVER if active else PANEL_LIGHT,
                text_color="#ffffff" if active else TEXT_DIM,
            )
        # При каждом открытии страницы — свежие данные из БД.
        if name == "tournaments":
            # Всегда показываем список, даже если до этого была открыта
            # рабочая область какого-то турнира.
            if hasattr(self, "tournament_detail_view"):
                self.tournament_detail_view.pack_forget()
                self.tournament_list_view.pack(fill="both", expand=True)
            self._refresh_tournament_list()
        elif name == "athletes" and hasattr(self, "_athletes_page"):
            self._athletes_page._refresh_list()
        elif name == "coaches" and hasattr(self, "_coaches_page"):
            self._coaches_page._refresh_list()
        elif name == "clubs" and hasattr(self, "_clubs_page"):
            self._clubs_page._refresh_list()

    def _build_tournaments_page(self):
        page = ctk.CTkFrame(self.main, fg_color=BG, corner_radius=0)
        self.pages["tournaments"] = page

        # ─── Вид 1: список турниров — занимает весь экран ───
        self.tournament_list_view = ctk.CTkFrame(page, fg_color=BG, corner_radius=0)
        self.tournament_list_view.pack(fill="both", expand=True)

        top = ctk.CTkFrame(self.tournament_list_view, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(16, 8))
        ctk.CTkLabel(top, text="Турниры",
                    font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.new_tournament_btn = ctk.CTkButton(
            top, text="➕  Создать турнир", height=38, width=170,
            fg_color=SUCCESS, hover_color=SUCCESS_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._new_tournament)
        self.new_tournament_btn.pack(side="right")
        self.import_tournament_btn = ctk.CTkButton(
            top, text="📥  Импорт соревнования", height=38, width=180,
            fg_color=ACCENT_DIM, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=13),
            command=self._import_tournament_dialog)
        self.import_tournament_btn.pack(side="right", padx=(0, 10))
        self.delete_tournament_btn = ctk.CTkButton(
            top, text="🗑  Удалить", height=38, width=110,
            fg_color=DANGER, hover_color=DANGER_HOVER,
            command=self._delete_tournament)
        self.delete_tournament_btn.pack(side="right", padx=(0, 10))

        ctk.CTkLabel(self.tournament_list_view, text="Выберите турнир:",
                    text_color=TEXT_DIM, font=ctk.CTkFont(size=11),
                    anchor="w").pack(fill="x", padx=20, pady=(0, 4))
        self.tournament_scroll = ctk.CTkScrollableFrame(
            self.tournament_list_view, fg_color=BG, orientation="vertical")
        self.tournament_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        # ─── Вид 2: рабочая область выбранного турнира ───
        self.tournament_detail_view = ctk.CTkFrame(page, fg_color=BG, corner_radius=0)

        self.header = ctk.CTkFrame(self.tournament_detail_view, height=96,
                                   fg_color=PANEL, corner_radius=0)
        self.header.pack(fill="x")
        self.header.pack_propagate(False)

        self.back_btn = ctk.CTkButton(self.header, text="←  Назад",
                    width=96, height=34,
                    fg_color=PANEL_LIGHT, hover_color=ACCENT_DIM,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    command=self._back_to_tournaments)
        self.back_btn.pack(side="left", padx=(14, 4), pady=13)

        self.title_label = ctk.CTkLabel(self.header,
                    text="Выберите или создайте турнир",
                    font=ctk.CTkFont(size=18, weight="bold"))
        self.title_label.pack(side="left", padx=(8, 0), pady=15)

        self.status_badge = ctk.CTkLabel(self.header, text="", text_color="#0d1117",
                    corner_radius=6, font=ctk.CTkFont(size=11, weight="bold"))
        self.status_badge.pack(side="left", padx=(0, 10), ipadx=8, ipady=3)

        # Кнопки статуса: «Начать соревнования» (скоро начнётся),
        # «Завершить/Возобновить» (идёт/закончен) и «Табло» — в общем
        # фрейме на grid, чтобы скрывать/показывать их без смены порядка.
        self.header_actions = ctk.CTkFrame(self.header, fg_color="transparent")
        self.header_actions.pack(side="right", padx=20, pady=13)

        self.start_btn = ctk.CTkButton(self.header_actions, text="▶  Начать соревнования",
                    width=190, height=34,
                    fg_color=SUCCESS, hover_color=SUCCESS_HOVER,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    command=self._start_tournament)
        self.start_btn.grid(row=0, column=0, padx=(0, 8))

        self.finish_btn = ctk.CTkButton(self.header_actions, text="🏁 Завершить турнир",
                    width=170, height=34,
                    fg_color=WARNING, hover_color=WARNING_HOVER,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    command=self._toggle_finish_tournament)
        self.finish_btn.grid(row=0, column=1, padx=(0, 8))

        self.display_btn = ctk.CTkButton(self.header_actions, text="📺 Табло",
                    width=110, height=34,
                    fg_color=ACCENT_DIM, hover_color=ACCENT_HOVER,
                    command=self._open_display_board)
        self.display_btn.grid(row=0, column=2)

        self.refresh_section_btn = ctk.CTkButton(self.header_actions, text="🔄 Обновить данные",
                    width=140, height=34,
                    fg_color="#223047", hover_color="#2a3a57",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    command=self._refresh_tournament_views)
        self.refresh_section_btn.grid(row=0, column=3)

        # ─── Перенос соревнования: экспорт / импорт / аварийный экспорт ───
        self.export_btn = ctk.CTkButton(self.header_actions, text="📦 Экспорт",
                    width=110, height=30,
                    fg_color="#1a3a5a", hover_color="#2a5a7a",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    command=self._export_tournament_dialog)
        self.export_btn.grid(row=1, column=0, padx=(0, 8), pady=(2, 0))

        self.import_btn = ctk.CTkButton(self.header_actions, text="📥 Импорт",
                    width=100, height=30,
                    fg_color="#1a3a5a", hover_color="#2a5a7a",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    command=self._import_tournament_dialog)
        self.import_btn.grid(row=1, column=1, padx=(0, 8), pady=(2, 0))

        self.emergency_export_btn = ctk.CTkButton(
                    self.header_actions, text="🚨 Аварийный экспорт",
                    width=150, height=30,
                    fg_color=DANGER, hover_color=DANGER_HOVER,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    command=self._emergency_export)
        self.emergency_export_btn.grid(row=1, column=2, padx=(0, 8), pady=(2, 0))

        self.transfer_status_label = ctk.CTkLabel(self.header_actions,
                    text="", font=ctk.CTkFont(size=11),
                    text_color=TEXT_DIM)
        self.transfer_status_label.grid(row=1, column=3, padx=(4, 0), pady=(2, 0))

        self.notebook = ctk.CTkTabview(self.tournament_detail_view, fg_color=BG)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.notebook.add("⚖️ Категории")
        self.notebook.add("👥 Участники")
        self.notebook.add("🏆 Сетки")

        self._build_categories_tab()
        self._build_participants_tab()
        self._build_brackets_tab()

    def _build_athletes_page(self):
        page = ctk.CTkFrame(self.main, fg_color=BG, corner_radius=0)
        self.pages["athletes"] = page
        self._athletes_page = AthletesWindow(page, self.db)
        self._athletes_page.pack(fill="both", expand=True)

    def _build_coaches_page(self):
        page = ctk.CTkFrame(self.main, fg_color=BG, corner_radius=0)
        self.pages["coaches"] = page
        self._coaches_page = CoachesWindow(page, self.db)
        self._coaches_page.pack(fill="both", expand=True)

    def _build_clubs_page(self):
        page = ctk.CTkFrame(self.main, fg_color=BG, corner_radius=0)
        self.pages["clubs"] = page
        self._clubs_page = ClubsWindow(page, self.db)
        self._clubs_page.pack(fill="both", expand=True)

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

        self.cat_age_filter_frame = ctk.CTkFrame(tab, fg_color="transparent")
        self.cat_age_filter_frame.pack(fill="x", padx=10, pady=(0, 5))
        self._cat_age_vars = {}
        self._age_filter_btn = None
        self._rebuild_age_filter()

        self.cat_list_frame = ScrollableFrame(tab, fg_color=BG)
        self.cat_list_frame.pack(fill="both", expand=True, padx=10, pady=5)

    def _age_filter_button_text(self):
        selected = [a for a, v in self._cat_age_vars.items() if v.get()]
        if not selected:
            return "🎚 Категории: ничего не выбрано"
        if len(selected) == len(self._cat_age_vars):
            return "🎚 Категории: все"
        if len(selected) == 1:
            return f"🎚 Категории: {selected[0]}"
        return f"🎚 Категории: {len(selected)} выбрано"

    def _rebuild_age_filter(self):
        """Пересоздаёт фильтр по возрастным категориям — только те, что реально
        есть в текущем турнире. По умолчанию включены все."""
        if self._age_filter_btn is not None:
            try:
                self._age_filter_btn.destroy()
            except Exception:
                pass
            self._age_filter_btn = None
        self._cat_age_vars = {}
        if not self.current_tournament_id:
            return
        cats = self.db.get_categories(self.current_tournament_id)
        ages = [c["age_category"] for c in cats if c["age_category"]]
        seen = []
        for a in ages:
            if a not in seen:
                seen.append(a)
        if not seen:
            return
        for age in seen:
            self._cat_age_vars[age] = ctk.BooleanVar(value=True)
        self._age_filter_btn = ctk.CTkButton(
            self.cat_age_filter_frame, text=self._age_filter_button_text(),
            fg_color="#223047", hover_color="#2a3a57", height=34, width=220,
            command=self._open_age_filter_popup)
        self._age_filter_btn.pack(side="left")

    def _open_age_filter_popup(self):
        """Выпадающий селект с мультивыбором возрастных категорий.
        Список живёт внутри того же окна (как _DropdownFrame в ui_theme),
        закрывается по клику мимо."""
        if self._age_filter_btn is None or not self._cat_age_vars:
            return
        if getattr(self, "_age_dropdown", None) is not None \
                and self._age_dropdown.winfo_exists() \
                and self._age_dropdown.winfo_viewable():
            self._close_age_dropdown()
            return

        ages = list(self._cat_age_vars.keys())
        toplevel = self.winfo_toplevel()
        dd = ctk.CTkFrame(toplevel, fg_color=PANEL, corner_radius=8,
                          border_width=1, border_color="#3d444d")
        self._age_dropdown = dd

        scroller = ctk.CTkScrollableFrame(dd, fg_color="transparent",
                                          corner_radius=0)
        scroller.pack(fill="both", expand=True, padx=6, pady=6)

        for age in ages:
            ctk.CTkCheckBox(scroller, text=age, variable=self._cat_age_vars[age],
                            font=ctk.CTkFont(size=13)).pack(anchor="w", padx=4, pady=2)

        bar = ctk.CTkFrame(dd, fg_color="transparent")
        bar.pack(fill="x", padx=6, pady=(0, 6))

        def select_all():
            for v in self._cat_age_vars.values():
                v.set(True)

        def clear():
            for v in self._cat_age_vars.values():
                v.set(False)

        def apply():
            self._close_age_dropdown()
            if self._age_filter_btn is not None:
                self._age_filter_btn.configure(text=self._age_filter_button_text())
            self._refresh_categories()

        ctk.CTkButton(bar, text="Выбрать все", width=110, height=28,
                      fg_color="#223047", hover_color="#2a3a57",
                      command=select_all).pack(side="left", padx=(0, 6))
        ctk.CTkButton(bar, text="Сброс", width=80, height=28,
                      fg_color="#3a1010", hover_color="#5a2020",
                      command=clear).pack(side="left", padx=(0, 6))
        ctk.CTkButton(bar, text="Применить", width=90, height=28,
                      fg_color="#1a4a2a", hover_color="#2a6a3a",
                      command=apply).pack(side="right")

        # Позиционируем под кнопкой внутри того же окна, с учётом scaling.
        scaling = dd._apply_widget_scaling(1.0) or 1.0
        dd.update_idletasks()
        width = 260
        content_h = len(ages) * 30 + 60
        avail_h = toplevel.winfo_height() / scaling
        x_root = self._age_filter_btn.winfo_rootx()
        y_root = self._age_filter_btn.winfo_rooty() + self._age_filter_btn.winfo_height()
        x = (x_root - toplevel.winfo_rootx()) / scaling
        y = (y_root - toplevel.winfo_rooty()) / scaling
        margin = 8
        space_below = avail_h - y - margin
        space_above = y - margin
        height = min(content_h, 360)
        if height > space_below:
            if height <= space_above:
                y -= height + margin
            elif space_below >= space_above and space_below > 60:
                height = space_below
            else:
                height = space_above
                y -= height + margin
        dd.configure(width=int(width / scaling), height=int(height / scaling))
        dd.place(x=int(x), y=int(y))
        dd.tkraise()
        dd.update_idletasks()

        # Закрытие по клику мимо — bind на верхнем окне, через after, чтобы
        # клик, открывший список, не закрыл его тут же.
        self._dd_bind_pending = dd.after(10, lambda: self._bind_dd_outside(dd))

    def _bind_dd_outside(self, dd):
        self._dd_bind_pending = None
        try:
            toplevel = dd.winfo_toplevel()
            self._dd_bind_id = toplevel.bind("<Button-1>", self._on_dd_outside,
                                             add="+")
        except Exception:
            self._dd_bind_id = None

    def _on_dd_outside(self, event):
        dd = getattr(self, "_age_dropdown", None)
        if dd is None or not dd.winfo_exists():
            return
        try:
            wpath = str(event.widget)
            if wpath.startswith(str(dd)) or wpath.startswith(str(self._age_filter_btn)):
                return
        except Exception:
            pass
        self._close_age_dropdown()

    def _close_age_dropdown(self):
        if getattr(self, "_dd_bind_pending", None) is not None:
            try:
                self.after_cancel(self._dd_bind_pending)
            except Exception:
                pass
            self._dd_bind_pending = None
        if getattr(self, "_dd_bind_id", None) is not None:
            try:
                toplevel = self.winfo_toplevel()
                toplevel.unbind("<Button-1>", self._dd_bind_id)
            except Exception:
                pass
            self._dd_bind_id = None
        dd = getattr(self, "_age_dropdown", None)
        if dd is not None and dd.winfo_exists():
            try:
                dd.place_forget()
                dd.destroy()
            except Exception:
                pass
        self._age_dropdown = None

    def _open_category_wizard(self):
        if not self.current_tournament_id:
            messagebox.showwarning("Нет турнира", "Сначала выберите турнир.")
            return
        if self._tournament_locked():
            return

        PLACEHOLDER = "— выберите —"

        _tournament = self.db.get_tournament(self.current_tournament_id)
        is_combined = bool(_tournament and _tournament["format_type"] == "combined")

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

        age_menu = OptionMenu(win, variable=age_var,
                    values=[PLACEHOLDER] + age_keys, width=360, command=refresh_weights)
        age_menu.pack(padx=20)

        ctk.CTkLabel(win, text="Весовая категория:").pack(anchor="w", padx=20, pady=(15, 5))
        weight_menu = OptionMenu(win, variable=weight_var,
                    values=[PLACEHOLDER], width=360, state="disabled")
        weight_menu.pack(padx=20)

        if is_combined:
            ctk.CTkLabel(win, text="Двоеборье — категория создаётся сразу на обе руки.",
                         text_color="#445566").pack(anchor="w", padx=20, pady=(15, 5))
        else:
            ctk.CTkLabel(win, text="Рука:").pack(anchor="w", padx=20, pady=(15, 5))
            OptionMenu(win, variable=hand_var,
                        values=["Правая", "Левая", "Обе"], width=360).pack(padx=20)

        def confirm():
            age = age_var.get()
            w = weight_var.get()
            if age == PLACEHOLDER or w == PLACEHOLDER:
                messagebox.showwarning("Ошибка", "Выберите возрастную и весовую категорию.")
                return
            hand = "Обе" if is_combined else hand_var.get()
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
            self._rebuild_age_filter()
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
        if self._cat_age_vars:
            selected = [age for age, var in self._cat_age_vars.items() if var.get()]
            if selected:
                cats = [c for c in cats if c["age_category"] in selected]
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
        if not messagebox.askyesno("Удалить", "Удалить категорию и всех её участников?"):
            return
        entered = simpledialog.askstring(
            "Подтверждение", "Введите пароль для удаления:", show="*", parent=self
        )
        if entered is None:
            return
        if entered != DELETE_PASSWORD:
            messagebox.showerror("Неверный пароль", "Удаление отменено.")
            return
        self.db.delete_category(cid)
        self._rebuild_age_filter()
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
        self.filter_cat_menu = OptionMenu(ctrl, variable=self.filter_cat_var,
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

        self.participants_scroll = ScrollableFrame(tab, fg_color=BG)
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
            count = BadgeGenerator.generate(filepath, tournament, participants, categories_map)
            messagebox.showinfo(
                "Готово",
                f"Бейджики сохранены ({count} шт.):\n{filepath}\n\n"
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
        dlg.configure(bg=PANEL)

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
        form.pack(fill="x", padx=10, pady=10)

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
            OptionMenu(form, variable=hand_var,
                        values=["Правая", "Левая", "Обе"], width=240
                        ).grid(row=3, column=1, padx=(0, 15), pady=6, sticky="w")

        # ── row 4: фото (как и было) ──
        ctk.CTkLabel(form, text="Фото:", anchor="e", width=110).grid(
            row=4, column=0, padx=(15, 8), pady=6, sticky="e")
        photo_path_var.set(existing["photo_path"] or "" if existing else "")

        def choose_photo():
            p = filedialog.askopenfilename(
                filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")])
            if not p:
                return
            if not is_configured():
                messagebox.showwarning(
                    "Cloudinary не настроен",
                    "Загрузка фото недоступна: на этом компьютере не заданы "
                    "переменные окружения CLOUDINARY_CLOUD_NAME / "
                    "CLOUDINARY_UPLOAD_PRESET.\n\nУчастник будет сохранён без фото.")
                return

            photo_status_lbl.configure(text="Загружаем…", text_color="#c9a227")
            upload_btn.configure(state="disabled")

            # Папка турнира вычисляется в ГЛАВНОМ потоке — SQLite-соединение
            # создано в нём и из фонового потока (worker ниже) его трогать
            # нельзя (sqlite3.ProgrammingError: objects created in a thread...).
            tournament = (self.db.get_tournament(self.current_tournament_id)
                          if self.current_tournament_id else None)
            folder = "athletes"
            if tournament:
                # Фото участника лежит в папке СВОЕГО турнира, а не в
                # общей "athletes" — так фото одного турнира не
                # смешиваются с фото другого, и при удалении участника
                # по папке понятно, что файл принадлежит турниру.
                folder = (tournament["photo_folder"]
                          or tournament_photo_folder(tournament["name"])
                          or "athletes")

            def worker():
                try:
                    url = upload_photo(p, folder=folder)
                except CloudinaryUploadError as e:
                    def on_error():
                        photo_status_lbl.configure(text=f"Ошибка: {e}", text_color=ERR)
                        upload_btn.configure(state="normal")
                    dlg.after(0, on_error)
                    return
                except Exception as e:
                    # Любая другая ошибка не должна застрелять диалог на
                    # «Загружаем…» навсегда — показываем и возвращаем кнопку.
                    def on_error(e=e):
                        photo_status_lbl.configure(text=f"Ошибка: {e}", text_color=ERR)
                        upload_btn.configure(state="normal")
                    dlg.after(0, on_error)
                    return

                def on_success():
                    photo_path_var.set(url)
                    photo_status_lbl.configure(text="✓ Загружено", text_color=OK)
                    upload_btn.configure(state="normal")
                dlg.after(0, on_success)

            Thread(target=worker, daemon=True).start()

        upload_btn = ctk.CTkButton(form, text="📷 Выбрать", width=90, height=28,
                    fg_color=ACCENT_DIM, hover_color=INFO_HOVER, command=choose_photo)
        upload_btn.grid(row=4, column=1, padx=(0, 0), pady=6, sticky="w")

        photo_status_lbl = ctk.CTkLabel(form, text="не выбрано", text_color="#445566",
                    anchor="w")
        photo_status_lbl.grid(row=4, column=1, padx=(100, 0), pady=6, sticky="w")

        if photo_path_var.get():
            photo_status_lbl.configure(text="✓ Фото есть", text_color=OK)

        # ── кнопка выбора спортсмена (ставим ПОСЛЕ объявления всех полей формы,
        #    чтобы choose_athlete/update_categories видели fields["club"] и т.д.) ──
        def choose_athlete():
            picker = tk.Toplevel(dlg)
            picker.title("Выбрать спортсмена")
            picker.geometry("470x580")
            picker.transient(dlg)
            picker.grab_set()

            search_var = ctk.StringVar()
            ctk.CTkEntry(picker, textvariable=search_var, width=380,
                        placeholder_text="🔍 Поиск по имени/фамилии...").pack(padx=10, pady=10)

            results_frame = ScrollableFrame(picker, fg_color=BG)
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
                            photo_status_lbl.configure(text="✓ Фото спортсмена", text_color=OK)
                        update_categories(a)
                        validate_form()
                        picker.destroy()
                    # Дата рождения — чтобы различать однофамильцев
                    # (5 Петров / 2 Даулета): ДД.ММ.ГГГГ и пол.
                    bd = (a["birth_date"] or "").strip()
                    bd_txt = ""
                    if bd:
                        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
                            try:
                                bd_txt = datetime.strptime(bd[:10], fmt).strftime("%d.%m.%Y")
                                break
                            except ValueError:
                                continue
                        if not bd_txt:
                            bd_txt = bd
                    gender_txt = "м" if a["gender"] == "M" else ("ж" if a["gender"] == "F" else "")
                    sub = f" · {bd_txt}" if bd_txt else ""
                    if gender_txt:
                        sub += f" · {gender_txt}"
                    ctk.CTkButton(results_frame,
                                text=f"{a['first_name']} {a['last_name']} ({a['club'] or '—'}){sub}",
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

        # Фото скачиваем в фоне (не в UI-потоке) и перерисовываем список,
        # когда они появятся в кэше. Если скачивать нечего — колбэк не
        # вызывается и повторной перерисовки не будет.
        urls = [p["photo_path"] for p in participants if "photo_path" in p.keys() and p["photo_path"]]
        def _photo_warm_done():
            try:
                if self.winfo_exists():
                    self.after(150, self._refresh_participants)
            except Exception:
                pass
        precache_photos(urls, on_done=_photo_warm_done)
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

        self.bracket_list = ScrollableFrame(tab, fg_color=BG)
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
                        command=lambda c=cat, h=hand: self._open_bracket_window(c, h)
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
                    text_color=TEXT_FAINT,
                    font=ctk.CTkFont(size=12),
                    justify="center").pack(padx=30, pady=18)
            return

        # Счётчики участников и категорий по всем турнирам одним запросом.
        p_rows = self.db.conn.execute(
            "SELECT tournament_id, COUNT(*) AS n FROM participants GROUP BY tournament_id").fetchall()
        c_rows = self.db.conn.execute(
            "SELECT tournament_id, COUNT(*) AS n FROM weight_categories GROUP BY tournament_id").fetchall()
        part_count = {r["tournament_id"]: r["n"] for r in p_rows}
        cat_count = {r["tournament_id"]: r["n"] for r in c_rows}

        for idx, t in enumerate(tournaments, 1):
            active = t["id"] == self.current_tournament_id
            tid = t["id"]

            row = ctk.CTkFrame(self.tournament_scroll, corner_radius=10,
                    fg_color=ACCENT_DIM if active else PANEL_LIGHT,
                    border_width=1,
                    border_color=ACCENT if active else CARD_BORDER)
            row.pack(fill="x", padx=12, pady=4)

            # Заголовок: номер + название (место в скобках) + статус
            head = ctk.CTkFrame(row, fg_color="transparent")
            head.pack(fill="x", padx=12, pady=(10, 0))
            num_lbl = ctk.CTkLabel(head, text=f"{idx}.", width=34, anchor="w",
                    font=ctk.CTkFont(size=14, weight="bold"),
                    text_color=ACCENT if not active else "#ffffff")
            num_lbl.pack(side="left")
            loc = f" ({t['location']})" if ("location" in t.keys() and t["location"]) else ""
            name_lbl = ctk.CTkLabel(head, text=f"🏅  {t['name']}{loc}", anchor="w",
                    font=ctk.CTkFont(size=14, weight="bold"),
                    text_color="#ffffff" if active else TEXT)
            name_lbl.pack(side="left", fill="x", expand=True)
            status = t["status"] if ("status" in t.keys() and t["status"]) else "active"
            if status == "upcoming":
                badge_text, badge_color = "СКОРО", "#ffcc00"
            elif status == "finished":
                badge_text, badge_color = "ОКОНЧЕН", "#ff6666"
            else:
                badge_text, badge_color = "ИДЁТ", "#4dff88"
            ctk.CTkLabel(head, text=badge_text,
                    fg_color=badge_color, text_color="#0d1117", corner_radius=5,
                    font=ctk.CTkFont(size=10, weight="bold"),
                    ).pack(side="right", ipadx=6, ipady=2)

            # Дата — крупно
            date_lbl = ctk.CTkLabel(row, text=f"📅  {t['date']}", anchor="w",
                    font=ctk.CTkFont(size=17, weight="bold"),
                    text_color="#ffffff" if active else TEXT)
            date_lbl.pack(fill="x", padx=14, pady=(5, 0))

            # Статистика: категории, участники, формат, система
            bracket = t["bracket_system"] if "bracket_system" in t.keys() else "double"
            ftype = t["format_type"] if "format_type" in t.keys() else "separate"
            fmt_bracket = "До 1 поражения" if bracket == "single" else "До 2 поражений"
            fmt_format = "Двоеборье" if ftype == "combined" else "На отдельных руках"

            stats = ctk.CTkFrame(row, fg_color="transparent")
            stats.pack(fill="x", padx=14, pady=(3, 10))
            stat_color = "#dfe8f3" if active else TEXT_DIM
            cat_lbl = ctk.CTkLabel(stats, text=f"Категорий: {cat_count.get(tid, 0)}",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=stat_color)
            cat_lbl.pack(side="left", padx=(0, 14))
            ctk.CTkLabel(stats, text=f"Участников: {part_count.get(tid, 0)}",
                    font=ctk.CTkFont(size=12), text_color=stat_color).pack(side="left", padx=(0, 14))
            ctk.CTkLabel(stats, text=f"Вид: {fmt_format}",
                    font=ctk.CTkFont(size=12), text_color=stat_color).pack(side="left", padx=(0, 14))
            ctk.CTkLabel(stats, text=f"Система: {fmt_bracket}",
                    font=ctk.CTkFont(size=12), text_color=stat_color).pack(side="left")

            # Вся строка кликабельна: 1 клик — выделить, 2 клика — открыть.
            def select(tid=tid):
                self._select_tournament(tid)

            def select_only(tid=tid):
                self._select_only(tid)

            clickables = [row, head, stats]
            clickables += list(head.winfo_children()) + list(row.winfo_children())
            clickables += list(stats.winfo_children())
            hover_labels = [num_lbl, name_lbl, date_lbl, cat_lbl]

            def set_hover(on, active=active, row=row, hover_labels=hover_labels):
                if active:
                    return
                if on:
                    row.configure(fg_color=ACCENT_DIM, border_color=ACCENT)
                    for w in hover_labels:
                        w.configure(text_color="#ffffff")
                else:
                    row.configure(fg_color=PANEL_LIGHT, border_color=CARD_BORDER)
                    for w in hover_labels:
                        w.configure(text_color=w._orig_color)
            # Храним исходный цвет для восстановления при уходе мыши.
            for w in hover_labels:
                w._orig_color = w.cget("text_color")

            for w in clickables:
                try:
                    w.bind("<Button-1>", lambda e, s=select_only: s(), add="+")
                    w.bind("<Double-Button-1>", lambda e, s=select: s(), add="+")
                    w.bind("<Enter>", lambda e, s=set_hover: s(True), add="+")
                    w.bind("<Leave>", lambda e, s=set_hover: s(False), add="+")
                except Exception:
                    pass

    def _select_only(self, tid):
        """Выделяет турнир в списке (1 клик), не открывая его.
        Перерисовка списка откладывается, чтобы второй клик (двойного
        клика) успел сработать до пересоздания виджетов."""
        self.current_tournament_id = tid
        if self._pending_select is not None:
            self.after_cancel(self._pending_select)
        self._pending_select = self.after(250, self._apply_select)

    def _apply_select(self):
        self._pending_select = None
        self._refresh_tournament_list()

    def _select_tournament(self, tid):
        if self._pending_select is not None:
            self.after_cancel(self._pending_select)
            self._pending_select = None
        self.current_tournament_id = tid
        t = self.db.get_tournament(tid)
        self.title_label.configure(
            text=f"🏆  {t['name']}  |  {t['date']}  |  {t['location'] or ''}")
        self._refresh_status_badge(t)
        self._refresh_tournament_list()
        self._rebuild_age_filter()
        self._refresh_categories()
        self._refresh_participants()
        self._refresh_brackets_tab()
        self._show_tournament_detail()
        self._reconcile_sync()

    def _show_tournament_detail(self):
        """Скрывает список турниров и открывает рабочую область выбранного."""
        self.tournament_list_view.pack_forget()
        self.tournament_detail_view.pack(fill="both", expand=True)

    def _back_to_tournaments(self):
        """Возврат из рабочей области турнира к полному списку турниров."""
        self.current_tournament_id = None
        self.tournament_detail_view.pack_forget()
        self.tournament_list_view.pack(fill="both", expand=True)
        self._refresh_tournament_list()

    def _refresh_tournament_views(self):
        """Кнопка «Обновить данные» в шапке турнира: перечитывает все разделы
        (категории, участники, сетки) из локальной БД и перерисовывает их.
        Данные могли измениться не через это окно (например скриптом, другим
        окном или после импорта) — кнопка приводит вкладки к актуальному виду."""
        if not self.current_tournament_id:
            return
        t = self.db.get_tournament(self.current_tournament_id)
        self.title_label.configure(
            text=f"🏆  {t['name']}  |  {t['date']}  |  {t['location'] or ''}")
        self._refresh_status_badge(t)
        self._rebuild_age_filter()
        self._refresh_categories()
        self._refresh_participants()
        self._refresh_brackets_tab()
        self._reconcile_sync()

    def _reconcile_sync(self):
        """Сверяет локальные матчи текущего турнира с картой id_map и ставит
        в очередь create_match для тех, что отсутствуют на сайте. Вызывается
        из кнопки «Обновить данные» и при открытии турнира, чтобы сетка
        самовосстанавливалась, если сервер потерял матчи."""
        try:
            from sync.sync_manager import sync_manager
            tid = self.current_tournament_id
            if not tid or not sync_manager.enabled:
                return
            added = sync_manager.reconcile_missing_matches(tid)
            if added:
                sync_manager.try_auto_flush_async()
        except Exception as e:
            print(f"[reconcile] ошибка: {e}")

    # ════════════════════════════════════════════════════════════════
    #  ЭКСПОРТ / ИМПОРТ СОРЕВНОВАНИЯ (.armwrestling)
    def _default_export_filename(self, tid):
        try:
            t = self.db.get_tournament(tid)
            name = re.sub(r'[\\/*?:"<>|]', "_", t["name"])[:40] or "competition"
            date = (t.get("date") or "date").replace(".", "_")
            return f"{name}_{date}.armwrestling"
        except Exception:
            return "competition.armwrestling"

    def _export_tournament_dialog(self):
        """Соревнование → Экспорт: проверка целостности, файл, проверка."""
        tid = self.current_tournament_id
        if not tid:
            return
        owner = _messagebox_owner()
        try:
            problems = validate_competition_integrity(self.db.conn, tid)
        except Exception as e:
            messagebox.showerror("Экспорт", f"Не удалось проверить данные: {e}",
                                 parent=owner)
            return
        if problems:
            messagebox.showerror(
                "Экспорт невозможен",
                "Соревнование содержит повреждённые данные — исправьте их "
                "перед экспортом:\n\n- " + "\n- ".join(problems[:8]),
                parent=owner)
            return
        dest = filedialog.asksaveasfilename(
            parent=owner, defaultextension=".armwrestling",
            filetypes=[("Соревнование", "*.armwrestling")],
            initialfile=self._default_export_filename(tid),
            title="Экспорт соревнования")
        if not dest:
            return
        password = None
        if messagebox.askyesno("Защита паролем",
                               "Защитить файл паролем?",
                               parent=owner):
            password = simpledialog.askstring("Пароль",
                                              "Введите пароль:",
                                              show="*", parent=owner)
            if password is None:
                return
        include_photos = messagebox.askyesno(
            "Фотографии", "Включить фотографии в архив?",
            parent=owner)
        try:
            metadata = export_competition(self.db.conn, sync_manager.state,
                                          tid, dest, password=password,
                                          include_photos=include_photos)
        except ExportError as e:
            messagebox.showerror("Экспорт", str(e), parent=owner)
            return
        except Exception as e:
            messagebox.showerror("Экспорт", f"Ошибка экспорта: {e}",
                                 parent=owner)
            return
        messagebox.showinfo(
            "Экспорт успешно создан",
            f"Файл:\n{dest}\n\n"
            f"Матчей: {metadata['counts']['matches']}, "
            f"завершено: {metadata['counts']['finished_matches']}\n"
            f"Синхронизация файла — резервная копия соревнования "
            "для переноса на другой компьютер.",
            parent=owner)

    def _emergency_export(self):
        """Аварийный экспорт: максимально быстро, без проверки целостности."""
        tid = self.current_tournament_id
        if not tid:
            return
        owner = _messagebox_owner()
        if not messagebox.askyesno("Аварийный экспорт",
                                   "Создать аварийную копию соревнования "
                                   "прямо сейчас?", parent=owner):
            return
        try:
            path = backup_manager.emergency_export(tid)
        except Exception as e:
            messagebox.showerror("Аварийный экспорт", str(e), parent=owner)
            return
        messagebox.showinfo("Аварийный экспорт",
                            f"Сохранено:\n{path}\n\n"
                            "Файл можно перенести на другой компьютер и "
                            "импортировать.", parent=owner)

    def _import_tournament_dialog(self):
        src = filedialog.askopenfilename(
            parent=_messagebox_owner(),
            filetypes=[("Соревнование", "*.armwrestling")],
            title="Импорт соревнования")
        if src:
            self._do_import_file(src)

    def _do_import_file(self, src, password=None, force=False):
        """Полный поток импорта: проверка файла → предпросмотр → транзакция."""
        owner = _messagebox_owner()
        try:
            metadata, summary = preview_archive(src, password)
        except BackupFormatError as e:
            if password is None and "парол" in str(e).lower():
                password = simpledialog.askstring(
                    "Пароль", str(e) + "\n\nВведите пароль:",
                    show="*", parent=owner)
                if password is None:
                    return
                self._do_import_file(src, password, force)
                return
            messagebox.showerror("Импорт", str(e), parent=owner)
            return
        except ImportValidationError as e:
            messagebox.showerror("Импорт: файл повреждён", str(e),
                                 parent=owner)
            return

        tid = summary["competition_id"]
        existing = self.db.get_tournament(tid)
        if existing and not force:
            same_session = True
            try:
                same_session = (existing["session_id"]
                                == summary.get("session_id"))
            except Exception:
                pass
            msg = (f"В приложении уже есть соревнование с таким ID:\n"
                   f"«{existing['name']}».\n\n"
                   "Импортировать файл и ЗАМЕНИТЬ данные существующего "
                   "соревнования?")
            if not same_session:
                msg = ("⚠️ Соревнование в файле создано в другой сессии "
                       "(другой компьютер/восстановление).\n\n" + msg)
            choice = messagebox.askyesnocancel(
                "Соревнование уже существует",
                msg + "\n\n«Да» — заменить (восстановить из файла)\n"
                      "«Нет» — открыть существующее\n"
                      "«Отмена» — не импортировать",
                parent=owner)
            if choice is None:
                return
            if not choice:
                self._select_tournament(tid)
                return
            force = True

        if not self._show_import_preview(summary):
            return

        try:
            result = import_competition(self.db.conn, sync_manager.state,
                                        src, password=password,
                                        force_replace=force,
                                        photos_dir=str(PHOTOS_DIR))
        except CompetitionExistsError as e:
            messagebox.showwarning("Соревнование уже существует",
                                   str(e), parent=owner)
            return
        except (IdCollisionError, ImportValidationError) as e:
            messagebox.showerror("Импорт невозможен", str(e), parent=owner)
            return
        except Exception as e:
            messagebox.showerror("Импорт не удался",
                                 f"Все изменения откачены.\n\n{e}",
                                 parent=owner)
            return

        self._refresh_tournament_list()
        messagebox.showinfo(
            "Соревнование восстановлено",
            f"«{result['name']}»\n\n"
            f"Матчей всего: {result['matches']}\n"
            f"Завершено: {result['finished']}\n"
            f"Осталось: {result['unfinished']}\n"
            f"Pending sync: {result['pending_operations']}\n\n"
            f"Последнее изменение: {result['last_modified_at']}",
            parent=owner)
        self._select_tournament(tid)

    def _show_import_preview(self, summary):
        """Окно предпросмотра перед импортом. Возвращает True, если
        пользователь подтвердил импорт."""
        dlg = tk.Toplevel(self)
        dlg.withdraw()
        dlg.title("Предпросмотр импорта")
        dlg.geometry("520x560")
        center_toplevel(dlg, 520, 560)
        dlg.configure(bg=PANEL)
        dlg.resizable(False, False)
        dlg.deiconify()

        confirmed = {"ok": False}
        ctk.CTkLabel(dlg, text="📥  Импорт соревнования",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(
                         pady=(22, 12))

        info = ctk.CTkFrame(dlg, fg_color="transparent")
        info.pack(fill="x", padx=35)
        rows = [
            ("Соревнование", summary.get("name")),
            ("Дата", summary.get("date")),
            ("Спортсменов", summary.get("athletes")),
            ("Тренеров", summary.get("coaches")),
            ("Клубов", summary.get("clubs")),
            ("Категорий", summary.get("categories")),
            ("Матчей", summary.get("matches")),
            ("Завершено", summary.get("finished")),
            ("Осталось", summary.get("unfinished")),
            ("Pending sync", summary.get("pending_operations")),
            ("Последнее изменение", summary.get("last_modified_at")),
        ]
        for label, value in rows:
            row = ctk.CTkFrame(info, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=label + ":",
                         width=180, anchor="w", text_color=TEXT_DIM,
                         font=ctk.CTkFont(size=12)).pack(side="left")
            ctk.CTkLabel(row, text=str(value), anchor="w",
                         font=ctk.CTkFont(size=12, weight="bold")).pack(
                             side="left")

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(pady=(24, 12))
        ctk.CTkButton(btns, text="Импортировать", width=150, height=38,
                      fg_color=SUCCESS, hover_color=SUCCESS_HOVER,
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=lambda: (confirmed.update(ok=True),
                                       dlg.destroy())).pack(
                          side="left", padx=8)
        ctk.CTkButton(btns, text="Отмена", width=120, height=38,
                      fg_color=DANGER, hover_color=DANGER_HOVER,
                      command=dlg.destroy).pack(side="left", padx=8)
        dlg.transient(self)
        try:
            dlg.grab_set()
        except Exception:
            pass
        self.wait_window(dlg)
        return confirmed["ok"]

    # ════════════════════════════════════════════════════════════════
    #  ИНДИКАТОР СОХРАННОСТИ + ВОССТАНОВЛЕНИЕ ПРИ СТАРТЕ
    # ════════════════════════════════════════════════════════════════
    def _status_tick(self):
        """Периодический индикатор: backup age + несинхронизированные
        операции + ошибки синхронизации."""
        try:
            if not getattr(self, "transfer_status_label", None):
                return
            label = self.transfer_status_label
            if not self.current_tournament_id:
                label.configure(text="")
                return
            pending = sync_manager.state.pending_count()
            latest = backup_manager.latest_backup()
            parts = []
            if latest is not None:
                age = int(latest["age"])
                if age < 60:
                    parts.append(f"Последний backup: {age} сек назад")
                elif age < 3600:
                    parts.append(f"Последний backup: {age // 60} мин назад")
                else:
                    parts.append(f"Последний backup: {age // 3600} ч назад")
            if pending:
                parts.append(f"Несинхронизировано: {pending}")
            if not parts:
                label.configure(
                    text="🟢 Все данные сохранены",
                    text_color="#4dff88")
            elif getattr(self, "_last_blocked", False):
                label.configure(
                    text="🔴 Есть ошибка синхронизации · "
                    + " · ".join(parts), text_color="#ff6666")
            else:
                label.configure(
                    text="🟡 " + " · ".join(parts),
                    text_color="#ffcc00")
        except Exception as e:
            print(f"[status] {e}")
        finally:
            self.after(2000, self._status_tick)

    def _startup_recovery_check(self):
        """При старте: целостность БД, незавершённые соревнования,
        последний backup."""
        try:
            ok, msg = backup_manager.check_integrity()
            if not ok:
                owner = _messagebox_owner()
                if messagebox.askyesno(
                        "Повреждена локальная БД",
                        msg + "\n\nВосстановить из последнего backup?",
                        parent=owner):
                    latest = backup_manager.latest_backup()
                    if latest and os.path.exists(latest["path"]):
                        self._do_import_file(latest["path"], force=True)
                    else:
                        messagebox.showwarning(
                            "Backup не найден",
                            "Нет файлов в папке backups/.\n"
                            "Импортируйте .armwrestling вручную.",
                            parent=owner)
                return
            unfinished = self.db.conn.execute(
                "SELECT id, name FROM tournaments "
                "WHERE status IN ('active','upcoming')").fetchall()
            latest = backup_manager.latest_backup()
            if unfinished and latest:
                owner = _messagebox_owner()
                age = int(latest["age"])
                choice = messagebox.askyesnocancel(
                    "Обнаружено незавершённое соревнование",
                    f"Найдено незавершённых соревнований: {len(unfinished)}\n"
                    f"Последний backup: {os.path.basename(latest['path'])}\n"
                    f"({age} сек назад)\n\n"
                    "«Да» — открыть соревнование\n"
                    "«Нет» — открыть файл backup\n"
                    "«Отмена» — не сейчас",
                    parent=owner)
                if choice is None:
                    return
                if choice:
                    self._select_tournament(unfinished[0]["id"])
                else:
                    self._import_tournament_dialog()
        except Exception as e:
            print(f"[transfer] recovery check: {e}")

    def _refresh_status_badge(self, tournament=None):
        """Обновляет бейдж статуса и кнопки по трём состояниям турнира:
        upcoming (скоро начнётся) — кнопка «Начать соревнования»;
        active (идёт) — кнопка «Завершить»; finished (закончен) — та же
        кнопка превращается в «Возобновить»."""
        if not self.current_tournament_id:
            self.status_badge.configure(text="")
            self.start_btn.grid_remove()
            self.finish_btn.grid_remove()
            return
        t = tournament or self.db.get_tournament(self.current_tournament_id)
        status = t["status"] if (t and "status" in t.keys() and t["status"]) else "active"
        if status == "upcoming":
            self.status_badge.configure(text="СКОРО НАЧНЁТСЯ", fg_color="#ffcc00")
            self.start_btn.grid()
            self.finish_btn.grid_remove()
        elif status == "finished":
            self.status_badge.configure(text="ЗАВЕРШЁН", fg_color="#ff6666")
            self.start_btn.grid_remove()
            self.finish_btn.grid()
            self.finish_btn.configure(text="↩️ Возобновить турнир",
                    fg_color="#1a3a5a", hover_color="#2a5a7a")
        else:
            self.status_badge.configure(text="ИДЁТ", fg_color="#4dff88")
            self.start_btn.grid_remove()
            self.finish_btn.grid()
            self.finish_btn.configure(text="🏁 Завершить турнир",
                    fg_color="#4a3a1a", hover_color="#6a5a2a")

    def _start_tournament(self):
        """Переводит турнир из «скоро начнётся» в статус «идёт»."""
        if not self.current_tournament_id:
            return
        self.db.start_tournament(self.current_tournament_id)
        from sync.sync_manager import sync_manager
        sync_manager.update_tournament_status(self.current_tournament_id, "in_progress")
        self._select_tournament(self.current_tournament_id)

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
                from club_rating import check_inactive_athletes, finalize_competition
                try:
                    finalize_competition(self.db.conn, self.current_tournament_id)
                    check_inactive_athletes(self.db.conn)
                except Exception as e:
                    print("club rating finalize error:", e)
                from sync.sync_manager import sync_manager
                sync_manager.update_tournament_status(self.current_tournament_id, "completed")
                # Завершение турнира — критическая операция: бэкап сразу.
                try:
                    backup_manager.autobackup_now(self.current_tournament_id)
                except Exception as e:
                    print(f"[backup] finish hook: {e}")
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
    
    def _open_bracket_window(self, category, hand):
        """Не даёт открыть сетку одной и той же категории/руки дважды —
        два окна над одними и теми же матчами расходятся по данным
        (например, оба назначают номер стола) и путают трансляцию на
        табло. Если окно уже открыто — просто поднимаем его наверх."""
        for w in getattr(self, "_open_bracket_windows", []):
            if w.winfo_exists() and w.category["id"] == category["id"] and w.hand == hand:
                w.deiconify()
                w.lift()
                w.focus()
                return
        BracketWindow(self, self.db, self.current_tournament_id, category, hand)

    def _new_tournament(self):
        dlg = tk.Toplevel(self)
        dlg.withdraw()
        dlg.title("Новый турнир")
        dlg.geometry("500x800")
        center_toplevel(dlg, 500, 800)
        dlg.minsize(420, 500)
        dlg.configure(bg=PANEL)
        dlg.resizable(True, True)
        dlg.deiconify()

        ctk.CTkLabel(dlg, text="🏆  Создать турнир",
                    font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(25, 15))

        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="x", padx=35)

        name_var = ctk.StringVar()
        date_var = ctk.StringVar()
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

        # Автоформат даты как в карточке спортсмена: вводишь цифры —
        # подставляется маска ДД.ММ.ГГГГ с проверкой дня/месяца/года.
        date_entry = entries["Дата *"]
        def format_date(event=None):
            now_year = datetime.now().year
            value = "".join(ch for ch in date_entry.get() if ch.isdigit())[:8]
            if len(value) >= 2:
                value = f"{min(31, max(1, int(value[:2]))):02d}" + value[2:]
            if len(value) >= 4:
                value = value[:2] + f"{min(12, max(1, int(value[2:4]))):02d}" + value[4:]
            if len(value) >= 8:
                value = value[:4] + f"{min(now_year + 10, max(now_year - 10, int(value[4:8]))):04d}"
            result = ""
            if len(value) >= 1:
                result += value[:2]
            if len(value) > 2:
                result += "." + value[2:4]
            if len(value) > 4:
                result += "." + value[4:]
            cursor = len(result)
            date_entry.delete(0, "end")
            date_entry.insert(0, result)
            date_entry.icursor(cursor)
        date_entry.bind("<KeyRelease>", format_date)

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
        OptionMenu(form, variable=format_var,
                    values=["На отдельных руках", "Двоеборье"],
                    width=380).pack(fill="x")

        ctk.CTkLabel(form, text="Система сетки", anchor="w",
                    font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(14, 2))
        system_var = ctk.StringVar(value="Double elimination (до двух поражений)")
        OptionMenu(form, variable=system_var,
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

    def _delete_tournament(self, tid=None):
        tid = tid or self.current_tournament_id
        if not tid:
            return
        t = self.db.get_tournament(tid)
        if not messagebox.askyesno("Удалить",
                    f"Удалить турнир «{t['name']}» и все данные?"):
            return

        entered = simpledialog.askstring(
            "Подтверждение", "Введите пароль для удаления:", show="*", parent=self
        )
        if entered is None:
            return
        if entered != DELETE_PASSWORD:
            messagebox.showerror("Неверный пароль", "Удаление отменено.")
            return

        self.db.delete_tournament(tid)
        if tid == self.current_tournament_id:
            self._back_to_tournaments()
        else:
            self._refresh_tournament_list()

    def on_close(self):
        if messagebox.askyesno("Выход", "Закрыть программу?"):
            self.db.close()
            self.destroy()

    def _start_auto_sync(self):
        """Запускает периодическую проверку подключения и авто-flush очереди."""
        self.after(10000, self._auto_sync_tick)

    def _start_pull_sync(self):
        """Обратная синхронизация: подтягивает в фоне карточки спортсменов,
        изменённые через админку сайта (см. sync/pull_sync.py). В отличие
        от _start_auto_sync (тикает на UI-потоке через self.after), сама
        сетевая часть тут крутится в ОТДЕЛЬНОМ фоновом потоке — если сайт
        недоступен/тормозит, интерфейс судьи это никак не подвесит."""
        from sync import pull_sync
        pull_sync.configure(db_path=str(DB_PATH), poll_interval=10)

    def _auto_sync_tick(self):
        try:
            from sync.sync_manager import sync_manager
            if sync_manager.state.pending_count() > 0:
                # Неблокирующий flush: сетевая часть (HTTP с таймаутом до 10с
                # на вызов) крутится в фоновом потоке, тикер на UI-потоке
                # мгновенно возвращается — интерфейс не замирает на
                # недоступном сервере.
                sync_manager.try_auto_flush_async()
            blocked = sync_manager.take_blocked_warning()
            self._last_blocked = bool(blocked)
            if blocked:
                ops = ", ".join(sorted({b["operation"] for b in blocked}))
                self._show_sync_toast(
                    f"⚠️ Не удаётся синхронизировать: {ops}. "
                    "Проверьте интернет и токен (desktop-app/.env). "
                    "Записи не потеряны — отправка повторится сама.")
            # Периодический авто-бэкап (не чаще min_interval, только если
            # были изменения — см. backup_manager.maybe_autobackup).
            try:
                backup_manager.maybe_autobackup(self.current_tournament_id)
            except Exception as e:
                print(f"[backup] tick: {e}")
        except Exception as e:
            # Тикер не должен умирать из-за одной ошибки (иначе синхронизация
            # молча останавливается навсегда — мы это уже ловили).
            print(f"[auto-sync] ошибка тикера: {e}")
        self.after(10000, self._auto_sync_tick)

    def _show_sync_toast(self, message):
        """Показывает сообщение-«тост» как оверлей ВНУТРИ активного окна, а не
        отдельным Toplevel. Отдельное окно на Windows заставляет ОС
        переключать Z-порядок, и рабочее окно (сетка) уходит в задний фон."""
        import tkinter as tk
        owner = _messagebox_owner() or self
        try:
            overlay = tk.Label(owner, text=message, bg="#1a3a5a", fg="#e0e0e0",
                               font=("Segoe UI", 11), padx=12, pady=8,
                               bd=1, relief="solid", highlightthickness=0)
            overlay.place(relx=0.5, rely=0.97, anchor="s", relwidth=0.6, height=36)
            overlay.lift()

            def _close():
                try:
                    overlay.destroy()
                except Exception:
                    pass
            overlay.after(3500, _close)
        except Exception:
            print(f"[toast] не удалось показать: {e}")


# ════
#  ЗАПУСК
# ════
if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
