from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EloHistory(Base):
    """История рейтинга Эло спортсмена: снимок elo после каждого
    завершённого турнира (по руке и по сумме рук).

    Записывается при завершении турнира (finalize_competition); для уже
    завершённых ранее турниров недостающие снимки создаются при старте
    приложения с текущими значениями. Существующие записи не перезаписываются,
    чтобы сохранить историческую последовательность.
    """

    __tablename__ = "elo_history"
    __table_args__ = (
        UniqueConstraint(
            "athlete_id",
            "competition_id",
            "hand",
            name="uq_elo_history_athlete_competition_hand",
        ),
        Index("ix_elo_history_athlete", "athlete_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False
    )
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False
    )

    # "left" | "right" | "both" (обе руки / суммарный рейтинг)
    hand: Mapped[str] = mapped_column(String(10), nullable=False)
    elo: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    athlete: Mapped["Athlete"] = relationship()
    competition: Mapped["Competition"] = relationship()
