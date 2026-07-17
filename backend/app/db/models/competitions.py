from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Competition(Base):
    """Турнир. status=draft создаётся десктопом сразу, как только
    организатор его завёл (реальное время, см. ARCHITECTURE.md §0/§5).
    status=published выставляется по кнопке "Опубликовать результаты" —
    только после этого турнир виден на публичном сайте."""

    __tablename__ = "competitions"
    __table_args__ = (
        CheckConstraint("status in ('draft','published')", name="ck_competitions_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    location_city_id: Mapped[int | None] = mapped_column(
        ForeignKey("cities.id", ondelete="SET NULL")
    )
    organizer: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    poster_path: Mapped[str | None] = mapped_column(String(500))
    regulations_doc_path: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    categories: Mapped[list["Category"]] = relationship(
        back_populates="competition", cascade="all, delete-orphan"
    )
    participants: Mapped[list["CompetitionParticipant"]] = relationship(
        back_populates="competition", cascade="all, delete-orphan"
    )


class CompetitionParticipant(Base):
    """Регистрация спортсмена на конкретный турнир (= бывшая participants из
    десктопа), но ссылается на постоянного Athlete вместо хранения ФИО
    заново. Поля *_at_event — "снимок" данных на момент турнира (вес мог
    отличаться от текущего веса в профиле спортсмена)."""

    __tablename__ = "competition_participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False
    )
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="RESTRICT"), nullable=False
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )

    weight_at_event: Mapped[float | None] = mapped_column(Float)
    club_at_event: Mapped[str | None] = mapped_column(String(200))
    coach_at_event: Mapped[str | None] = mapped_column(String(200))
    seed: Mapped[int | None] = mapped_column(Integer)
    bib_barcode: Mapped[str | None] = mapped_column(String(30))

    competition: Mapped["Competition"] = relationship(back_populates="participants")
    athlete: Mapped["Athlete"] = relationship()
    category: Mapped["Category"] = relationship()
