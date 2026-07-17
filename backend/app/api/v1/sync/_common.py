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