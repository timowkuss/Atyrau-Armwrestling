from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AthleteRanking(Base):
    __tablename__ = "athlete_rankings"

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False
    )
    scope_weight_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("weight_categories.id", ondelete="SET NULL")
    )
    scope_gender: Mapped[str | None] = mapped_column(String(10))
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    position: Mapped[int | None] = mapped_column(Integer)
    period: Mapped[str | None] = mapped_column(String(20))  # напр. "2026", "all-time"
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ClubRanking(Base):
    __tablename__ = "club_rankings"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False
    )
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gold_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    silver_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bronze_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    position: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
