from datetime import date, datetime


def parse_flexible_date(value: str) -> date:
    """Принимает дату либо в формате десктопа (ДД.ММ.ГГГГ), либо ISO
    (ГГГГ-ММ-ДД) — десктоп-приложение присылает первый вариант."""
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: {value}")


def normalize_full_name(name: str) -> str:
    """Приводит ФИО к каноническому виду для сравнения дублей: регистр
    вниз + слова по алфавиту. Так «Пётр Петров» и «Петров Пётр» считаются
    одним человеком — раньше порядок слов не учитывался, и тот же человек
    уезжал на сервер второй раз под новым id (дубли-карточки на сайте).
    Общий для спортсменов и тренеров (см. sync/athletes.py и
    sync/coaches.py)."""
    return " ".join(sorted(name.strip().lower().split()))