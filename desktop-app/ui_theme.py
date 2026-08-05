"""Единая тема интерфейса: палитра, шрифты, отступы и переиспользуемые
компоненты для всего приложения. Меняя цвета здесь, вы меняете стиль
одновременно во всех окнах. Бизнес-логики в этом модуле нет — только
внешний вид (ctk-виджеты строятся теми же API, что и раньше)."""

import tkinter as tk

import customtkinter as ctk

# ─── Палитра ──────────────────────────────────────────────────
BG = "#0d1117"            # фон приложения
PANEL = "#161b22"         # панели/шапки
PANEL_LIGHT = "#1c2129"   # карточки, hover панелей
CARD = "#151b23"          # карточки списков
CARD_ALT = "#1a2028"      # зебра / лёгкий контраст карточек
INPUT_BG = "#0d1117"      # поля ввода
BORDER = "#2d333b"        # рамки полей/панелей
BORDER_ACTIVE = "#3d444d"

# Выпадающие списки (dropdown) — фон чуть светлее панелей, чтобы список
# не сливался с карточками/фоном приложения.
DROPDOWN_BG = "#21262d"
DROPDOWN_HOVER = "#30363d"

# Текст
TEXT = "#e6edf3"          # основной текст
TEXT_DIM = "#9aa7b4"      # второстепенный
TEXT_FAINT = "#6e7681"    # подписи/подсказки
TEXT_BRIGHT = "#ffffff"

# Акценты
ACCENT = "#2f81f7"        # основной синий
ACCENT_HOVER = "#58a6ff"
ACCENT_DIM = "#1f6feb"
SUCCESS = "#238636"
SUCCESS_HOVER = "#2ea043"
WARNING = "#9e6a03"
WARNING_HOVER = "#d29922"
DANGER = "#8b1a1a"
DANGER_HOVER = "#b62324"
INFO = "#1f6feb"
INFO_HOVER = "#388bfd"

# Статусы
OK = "#3fb950"
ERR = "#f85149"
WARN = "#d29922"
GOLD = "#e3b341"

# Тонкие акценты карточек
CARD_BORDER = "#2d333b"
SELECTED = "#1f3a5f"

# ─── Шрифты ──────────────────────────────────────────────────
FONT_FAMILY = "Segoe UI"


def font(size=13, weight="normal", family=FONT_FAMILY):
    return ctk.CTkFont(size=size, weight=weight, family=family)


H1 = lambda: font(20, "bold")          # заголовок окна/экрана
H2 = lambda: font(16, "bold")          # заголовок карточки
H3 = lambda: font(13, "bold")          # подзаголовок
BODY = lambda: font(13)                # обычный текст
META = lambda: font(11)                # дополнительный текст
TAG = lambda: font(10, "bold")         # бейджи/теги


# ─── Компоненты ──────────────────────────────────────────────
def make_panel(parent, **kw):
    """Карточка-панель с рамкой."""
    kw.setdefault("fg_color", PANEL)
    kw.setdefault("corner_radius", 12)
    kw.setdefault("border_width", 1)
    kw.setdefault("border_color", CARD_BORDER)
    return ctk.CTkFrame(parent, **kw)


def make_card(parent, **kw):
    """Карточка для списков."""
    kw.setdefault("fg_color", CARD)
    kw.setdefault("corner_radius", 10)
    kw.setdefault("border_width", 1)
    kw.setdefault("border_color", CARD_BORDER)
    return ctk.CTkFrame(parent, **kw)


def button(parent, text, **kw):
    """Стилизованная кнопка."""
    kw.setdefault("fg_color", ACCENT_DIM)
    kw.setdefault("hover_color", ACCENT_HOVER)
    kw.setdefault("corner_radius", 8)
    kw.setdefault("font", BODY())
    return ctk.CTkButton(parent, text=text, **kw)


def primary_button(parent, text, **kw):
    kw.setdefault("fg_color", SUCCESS)
    kw.setdefault("hover_color", SUCCESS_HOVER)
    return button(parent, text, **kw)


def danger_button(parent, text, **kw):
    kw.setdefault("fg_color", DANGER)
    kw.setdefault("hover_color", DANGER_HOVER)
    return button(parent, text, **kw)


def ghost_button(parent, text, **kw):
    """Ненавязчивая кнопка второго плана."""
    kw.setdefault("fg_color", PANEL_LIGHT)
    kw.setdefault("hover_color", "#2a313c")
    kw.setdefault("border_width", 1)
    kw.setdefault("border_color", BORDER)
    return ctk.CTkButton(parent, text=text, **kw)


def icon_button(parent, text, **kw):
    """Компактная кнопка-иконка (✏️/🗑 и т.п.)."""
    kw.setdefault("width", 34)
    kw.setdefault("height", 30)
    kw.setdefault("fg_color", PANEL_LIGHT)
    kw.setdefault("hover_color", "#2a313c")
    kw.setdefault("corner_radius", 7)
    kw.setdefault("font", font(12))
    return ctk.CTkButton(parent, text=text, **kw)


def entry(parent, **kw):
    """Поле ввода в едином стиле."""
    kw.setdefault("fg_color", INPUT_BG)
    kw.setdefault("border_color", BORDER)
    kw.setdefault("corner_radius", 8)
    kw.setdefault("font", BODY())
    return ctk.CTkEntry(parent, **kw)

def option_menu(parent, **kw):
    kw.setdefault("fg_color", INPUT_BG)
    kw.setdefault("button_color", ACCENT_DIM)
    kw.setdefault("button_hover_color", ACCENT_HOVER)
    kw.setdefault("dropdown_fg_color", DROPDOWN_BG)
    kw.setdefault("dropdown_hover_color", DROPDOWN_HOVER)
    kw.setdefault("text_color", TEXT)
    kw.setdefault("corner_radius", 8)
    kw.setdefault("font", BODY())
    return OptionMenu(parent, **kw)


class _DropdownFrame(ctk.CTkFrame):
    """Выпадающий список, живущий ВНУТРИ того же окна, что и OptionMenu.

    Раньше использовался отдельный CTkToplevel, для которого приходилось
    перехватывать grab_set модального диалога и вешать глобальный bind_all
    («чтобы клики доходили»). На Windows это ломало повторное открытие и
    могло подвесить всё окно. Здесь список — обычный дочерний виджет:
    grab диалога сам пропускает клики в дочерние виджеты, а закрытие по
    клику мимо ловится bind'ом на верхнем окне. Никаких grab-трюков."""

    def __init__(self, parent, values, command, fg_color, hover_color,
                 text_color, font):
        super().__init__(parent, fg_color=fg_color, corner_radius=8,
                         border_width=1, border_color="#3d444d")
        self._fg_color = fg_color
        self._hover_color = hover_color
        self._text_color = text_color
        self._font = font
        self._values = list(values)
        self._command = command
        self._current = None
        self._buttons = []

        self._bind_id = None
        self._bind_pending = None
        self._rebuild()
        self.place_forget()

    def _rebuild(self):
        for b in self._buttons:
            b.destroy()
        self._buttons = []
        for value in self._values:
            selected = (value == self._current)
            btn = ctk.CTkButton(
                self,
                text=("✓ " if selected else "  ") + value,
                fg_color="transparent",
                hover_color=self._hover_color,
                text_color=(ACCENT_HOVER if selected else self._text_color),
                font=self._font,
                corner_radius=6,
                anchor="w",
                height=32,
                command=lambda v=value: self._select(v))
            btn.pack(fill="x", padx=4, pady=2)
            self._buttons.append(btn)

    def open(self, x_root, y_root, current=None, values=None):
        if values is not None:
            self._values = list(values)
        self._current = current
        self._rebuild()
        self.update_idletasks()
        # winfo_* возвращают физические пиксели, а place()/configure()
        # внутри CTk умножают значения на widget scaling — делим обратно,
        # иначе при DPI-масштабировании список уезжает вниз-вправо.
        scaling = self._apply_widget_scaling(1.0) or 1.0
        width = max((b.winfo_reqwidth() for b in self._buttons), default=140) + 12
        height = len(self._buttons) * 36 + 8
        self.configure(width=int(width / scaling), height=int(height / scaling))
        self.update_idletasks()
        toplevel = self.winfo_toplevel()
        # пересчитываем экранные координаты в координаты верхнего окна
        x = (x_root - toplevel.winfo_rootx()) / scaling
        y = (y_root - toplevel.winfo_rooty()) / scaling
        # если снизу не влезает — показываем список выше виджета
        avail_h = toplevel.winfo_height() / scaling
        if y + height > avail_h and y - height > 0:
            y -= height + 8
        self.place(x=int(x), y=int(y))
        self.tkraise()
        # закрытие по клику мимо ловим bind'ом на верхнем окне; привязку
        # регистрируем через after(), чтобы клик, который ОТКРЫЛ список,
        # не закрыл его тут же.
        if self._bind_id is None and self._bind_pending is None:
            self._bind_pending = self.after(10, self._bind_outside_click)

    def _bind_outside_click(self):
        self._bind_pending = None
        try:
            toplevel = self.winfo_toplevel()
            self._bind_id = toplevel.bind("<Button-1>", self._on_outside_click,
                                          add="+")
        except Exception:
            self._bind_id = None

    def _on_outside_click(self, event):
        try:
            wpath = str(event.widget)
            if wpath.startswith(str(self)):
                return
            self.close()
        except Exception:
            self.close()

    def close(self):
        if self._bind_pending is not None:
            try:
                self.after_cancel(self._bind_pending)
            except Exception:
                pass
            self._bind_pending = None
        if self._bind_id is not None:
            try:
                toplevel = self.winfo_toplevel()
                toplevel.unbind("<Button-1>", self._bind_id)
            except Exception:
                pass
            self._bind_id = None
        try:
            self.place_forget()
        except Exception:
            pass

    def is_open(self):
        try:
            return bool(self.winfo_viewable())
        except Exception:
            return False

    def _select(self, value):
        self.close()
        if self._command is not None:
            self._command(value)


class OptionMenu(ctk.CTkOptionMenu):
    """CTkOptionMenu, чей выпадающий список рисуется сам (см.
    _DropdownFrame) как дочерний виджет окна, а не нативным tk.Menu.
    Список создаётся лениво — только при первом открытии."""

    def __init__(self, master, **kw):
        self._dd_fg = kw.get("dropdown_fg_color") or DROPDOWN_BG
        self._dd_hover = kw.get("dropdown_hover_color") or DROPDOWN_HOVER
        self._dd_text = kw.get("dropdown_text_color") or TEXT
        self._dd_font = kw.get("dropdown_font") or BODY()
        super().__init__(master, **kw)
        try:
            self._dropdown_menu.destroy()
        except Exception:
            pass
        self._dropdown_menu = _LazyDropdown(self, self._dropdown_callback,
                                            self._dd_fg, self._dd_hover,
                                            self._dd_text, self._dd_font)
        # ctk хранит флаг _close_on_next_click и не сбрасывает его после
        # выбора пункта — второй клик (без повторного <Enter>) «закрывал» уже
        # закрытое меню вместо открытия. Полностью обходим его логику.
        self._close_on_next_click = False

    def _clicked(self, event=0):
        if self._state is not tk.DISABLED and len(self._values) > 0:
            if self._dropdown_menu.is_open():
                self._dropdown_menu.close()
            else:
                self._open_dropdown_menu()


class _LazyDropdown:
    """Заглушка, имитирующая API нативного DropdownMenu; настоящий список
    создаётся только при первом открытии и затем переиспользуется."""

    def __init__(self, om, callback, fg, hover, text, font):
        self._om = om
        self._callback = callback
        self._fg = fg
        self._hover = hover
        self._text = text
        self._font = font
        self._menu = None

    def open(self, x, y):
        # Список переиспользуем: создание новых окон на каждый клик тормозило.
        # Значения обновляем каждый раз (меняются через configure).
        if self._menu is not None:
            try:
                if not self._menu.winfo_exists():
                    self._menu = None
            except Exception:
                self._menu = None
        if self._menu is None:
            parent = self._om.winfo_toplevel()
            self._menu = _DropdownFrame(parent, self._om._values,
                                        self._callback, self._fg,
                                        self._hover, self._text, self._font)
        self._menu.open(x, y, current=self._om.get(), values=self._om._values)

    def close(self):
        if self._menu is not None and self._menu.winfo_exists():
            self._menu.close()

    def is_open(self):
        try:
            return bool(self._menu is not None and self._menu.winfo_exists()
                        and self._menu.is_open())
        except Exception:
            return False

    def configure(self, **kw):
        if "values" in kw:
            kw.pop("values")
        if "fg_color" in kw:
            self._fg = kw.pop("fg_color")
        if "hover_color" in kw:
            self._hover = kw.pop("hover_color")
        if "text_color" in kw:
            self._text = kw.pop("text_color")
        if "font" in kw:
            self._font = kw.pop("font")
        if self._menu is not None:
            self._menu.configure(**kw)

    def cget(self, name):
        if name == "fg_color":
            return self._fg
        if name == "hover_color":
            return self._hover
        if name == "text_color":
            return self._text
        if name == "font":
            return self._font
        if name == "values":
            return list(self._om._values)
        return None


def label(parent, text, **kw):
    kw.setdefault("font", BODY())
    kw.setdefault("text_color", TEXT)
    return ctk.CTkLabel(parent, text=text, **kw)


def section_label(parent, text):
    """Заголовок-подзаголовок секции внутри панели."""
    return ctk.CTkLabel(parent, text=text, font=H3(), text_color=TEXT_DIM,
                        anchor="w")


def badge(parent, text, color=OK, **kw):
    kw.setdefault("text_color", "#0d1117")
    kw.setdefault("fg_color", color)
    kw.setdefault("corner_radius", 6)
    kw.setdefault("font", TAG())
    kw.setdefault("ipadx", 8)
    kw.setdefault("ipady", 3)
    return ctk.CTkLabel(parent, text=text, **kw)


def search_entry(parent, **kw):
    """Поле поиска с иконкой-подсказкой в placeholder."""
    kw.setdefault("height", 36)
    kw.setdefault("border_width", 1)
    return entry(parent, **kw)


# ─── Глобальные настройки темы ────────────────────────────────
class Theme:
    """Тонкий фасад: держит в себе все стилизующие функции."""

    panel = staticmethod(make_panel)
    card = staticmethod(make_card)
    button = staticmethod(button)
    primary_button = staticmethod(primary_button)
    danger_button = staticmethod(danger_button)
    ghost_button = staticmethod(ghost_button)
    icon_button = staticmethod(icon_button)
    entry = staticmethod(entry)
    option_menu = staticmethod(option_menu)
    OptionMenu = OptionMenu
    label = staticmethod(label)
    section_label = staticmethod(section_label)
    badge = staticmethod(badge)

    def apply_global(self, ctk_module):
        """Применяет общую тёмную тему ко всем виджетам, у которых не задан
        собственный цвет (фолбэки customtkinter)."""
        ctk_module.set_appearance_mode("dark")
        ctk_module.set_default_color_theme("blue")
        # Прозрачные "прилипшие" фоны глобально не трогаем — каждая панель
        # задаёт свой цвет явно через компоненты выше.


theme = Theme()
