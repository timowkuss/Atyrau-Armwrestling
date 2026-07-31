from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ClubRating(Base):
    """Текущий рейтинг клуба (аккумулятор баллов).

    rating никогда не опускается ниже нуля — отрицательные значения
    клампим в 0 в сервисе club_rating. Историческая таблица хранит при
    этом реальные (в т.ч. отрицательные) изменения, см. ClubRatingHistory.
    """

    __tablename__ = "club_rating"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    rating: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    club: Mapped["Club"] = relationship()


class ClubRatingHistory(Base):
    """Журнал изменений рейтинга клуба.

    КАЖДОЕ изменение рейтинга обязательно записывается сюда (транзакцией
    вместе с обновлением club_rating). points — реальная дельта, которая
    может быть отрицательной (штрафы); клубный рейтинг при этом клампится
    в 0, но история сохраняет реальное значение.

    Уникальный ключ (club_id, athlete_id, tournament_id, reason, description)
    защищает от повторного начисления: дублирующий вызов add_points просто
    не создаёт вторую запись.
    """

    __tablename__ = "club_rating_history"
    __table_args__ = (
        UniqueConstraint(
            "club_id",
            "athlete_id",
            "tournament_id",
            "reason",
            "description",
            name="uq_club_rating_history",
        ),
        Index("ix_club_rating_history_club", "club_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False
    )
    athlete_id: Mapped[int | None] = mapped_column(
        ForeignKey("athletes.id", ondelete="SET NULL")
    )
    tournament_id: Mapped[int | None] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE")
    )
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    club: Mapped["Club"] = relationship()
    athlete: Mapped["Athlete | None"] = relationship()
    tournament: Mapped["Competition | None"] = relationship()
