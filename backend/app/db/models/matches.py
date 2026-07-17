from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Match(Base):
    """Структура полностью повторяет таблицу matches из существующего
    десктоп-приложения (движок DoubleEliminationEngine не переписывается) —
    только p1_id/p2_id/winner_id теперь ссылаются на
    competition_participants вместо локальных participants."""

    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )

    hand: Mapped[str] = mapped_column(String(20), default="Правая", nullable=False)
    round_name: Mapped[str | None] = mapped_column(String(50))
    bracket: Mapped[str] = mapped_column(String(20), default="winners", nullable=False)
    match_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    p1_id: Mapped[int | None] = mapped_column(
        ForeignKey("competition_participants.id", ondelete="SET NULL")
    )
    p2_id: Mapped[int | None] = mapped_column(
        ForeignKey("competition_participants.id", ondelete="SET NULL")
    )
    winner_id: Mapped[int | None] = mapped_column(
        ForeignKey("competition_participants.id", ondelete="SET NULL")
    )

    p1_losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    p2_losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_bye: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)

    win_next_id: Mapped[int | None] = mapped_column(
        ForeignKey("matches.id", ondelete="SET NULL")
    )
    win_next_slot: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    lose_next_id: Mapped[int | None] = mapped_column(
        ForeignKey("matches.id", ondelete="SET NULL")
    )
    lose_next_slot: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
