from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AthleteStatistic(Base):
    """Агрегированная статистика спортсмена. Пересчитывается автоматически
    stats_engine.py после публикации турнира — ЗА ИСКЛЮЧЕНИЕМ случая, когда
    is_manual_override=True: тогда пересчёт для этого спортсмена
    пропускается, пока админ сам не снимет флаг через
    POST /admin/athletes/{id}/statistics/recalculate (см. ARCHITECTURE.md
    §3.4, §4.2, §6)."""

    __tablename__ = "athlete_statistics"

    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), primary_key=True
    )

    total_competitions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    left_hand_wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    left_hand_losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    right_hand_wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    right_hand_losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    gold_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    silver_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bronze_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_manual_override: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    overridden_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    athlete: Mapped["Athlete"] = relationship(back_populates="statistics")
