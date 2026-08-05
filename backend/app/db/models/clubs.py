from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Club(Base):
    __tablename__ = "clubs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    logo_path: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(String(300))
    city_id: Mapped[int | None] = mapped_column(
        ForeignKey("cities.id", ondelete="SET NULL")
    )
    founded_date: Mapped[date | None] = mapped_column(Date)
    phone: Mapped[str | None] = mapped_column(String(30))
    rating_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    city = relationship("City")
    coaches: Mapped[list["Coach"]] = relationship(back_populates="club")
    athletes: Mapped[list["Athlete"]] = relationship(back_populates="club")


def _normalize_club_name(name: str) -> str:
    """Канонический вид названия клуба для сравнения дублей: регистр вниз,
    схлопываем лишние пробелы + слова по алфавиту. Так «Спортивный клуб
    Алга» и «Алга Спортивный клуб» считаются одним клубом — раньше порядок
    слов не учитывался, и тот же клуб мог уехать на сервер второй раз под
    новым id после потери id_map на десктопе (как у спортсменов/тренеров)."""
    return " ".join(sorted(name.strip().lower().split()))


def find_club_by_name(db, name: str | None) -> Club | None:
    """Клуб с таким именем (без учёта регистра и порядка слов) или None.

    Используется для дедупа в create_club (sync + admin): повторное создание
    клуба с уже существующим именем возвращает существующий, а не плодит
    дубли (см. миграцию b1c2d3e4f5a6 — уникальный индекс на lower(name)).

    Сначала пробуем запрос через lower() — он корректен в Postgres (прод).
    Фолбэк-скан в Python страхует SQLite (используется в тестах): там
    lower() не понимает кириллицу и возвращает строку без изменений."""
    norm = (name or "").strip().lower()
    if not norm:
        return None
    key = _normalize_club_name(norm)
    if not key:
        return None
    club = db.query(Club).filter(func.lower(Club.name) == norm).first()
    if club is not None:
        return club
    for candidate in db.query(Club).all():
        if _normalize_club_name(candidate.name or "") == key:
            return candidate
    return None
